"""FlowSuite — one local voice engine, three hotkeys.

Merges WhisperFlow (prose dictation) and CoderFlow (voice coding) into a
single always-on process that shares ONE whisper model and ONE microphone
stream. Push-to-talk, fully on-device, injects at the cursor in *any* app:

    Hold F10  ->  prose dictation   (fillers stripped, capitalized)
    Hold F8   ->  Python code       (spoken_python transpiler)
    Hold F9   ->  C++ code          (raw text until spoken_cpp is built)

Release to insert. Nothing ever leaves this machine.
"""

import glob
import json
import os
import site
import sys
import threading
import time
from pathlib import Path


def _enable_cuda_dlls() -> None:
    """faster-whisper/ctranslate2 loads cublas/cudnn by *bare name*, which
    Windows resolves via PATH only (os.add_dll_directory does not cover it).
    The `nvidia-*-cu12` pip wheels drop the DLLs under site-packages/nvidia/*/bin,
    so prepend those to PATH before the model is ever loaded. No-op if absent."""
    dirs = []
    for root in site.getsitepackages() + [site.getusersitepackages()]:
        dirs += glob.glob(os.path.join(root, "nvidia", "*", "bin"))
    if dirs:
        os.environ["PATH"] = os.pathsep.join(dirs) + os.pathsep + os.environ["PATH"]


_enable_cuda_dlls()

from pynput import keyboard as pynput_keyboard
from pynput.keyboard import Controller as KeyController, Key

# reuse the building blocks already proven in the two apps
from whisperflow import Recorder, SAMPLE_RATE, beep, parse_hotkey, clean_text, IS_MAC
import spoken_python
import spoken_cpp

_TRANSPILERS = {"python": spoken_python, "cpp": spoken_cpp}

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "flowsuite_config.json"

# identifier-bias ONLY. Do NOT list punctuation words ("comma/colon/bracket")
# here — priming whisper with them makes it hallucinate those words into the
# transcript. Keep it to variable/keyword tokens, no punctuation.
_CODE_PROMPT = (
    "dp nums idx res left right mid cnt tmp ans total i j k n m target result "
    "count start end low high node root curr prev head val seen visited stack "
    "queue graph grid heap for while if elif else return continue break range "
    "len enumerate zip sorted reversed append pop min max sum abs set list dict "
    "map filter defaultdict Counter deque heapq True False None"
)

DEFAULT_CONFIG = {
    "model_size": "small",
    "device": "cuda",            # RTX 3050; auto-falls back to cpu/int8
    "compute_type": "float16",
    "language": "en",
    "beep": True,
    "min_record_seconds": 0.3,
    "key_delay": 0.02,
    "remove_fillers": True,
    # hotkey -> mode.  modes: "prose" | "python" | "cpp"
    "hotkeys": {"f10": "prose", "f8": "python", "f9": "cpp"},
    "code_initial_prompt": _CODE_PROMPT,
    "identifier_aliases": {
        "d p": "dp", "gnomes": "nums", "index": "idx",
    },
}

_KEY_MAP = {"enter": Key.enter, "tab": Key.tab, "backspace": Key.backspace}


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[config] could not read {CONFIG_PATH.name} ({e}); defaults")
    else:
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2),
                               encoding="utf-8")
        print(f"[config] wrote default config to {CONFIG_PATH}")
    return cfg


class FlowSuite:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.busy = False
        self.active_mode: str | None = None
        self._kbd = KeyController()

        print(f"[model] loading faster-whisper '{cfg['model_size']}' on "
              f"{cfg['device']} ({cfg['compute_type']}) ...")
        from faster_whisper import WhisperModel
        t0 = time.time()
        try:
            self.model = WhisperModel(cfg["model_size"], device=cfg["device"],
                                      compute_type=cfg["compute_type"])
        except (RuntimeError, ValueError) as e:
            print(f"[model] {cfg['device']} unavailable ({e}); using cpu/int8")
            self.model = WhisperModel(cfg["model_size"], device="cpu",
                                      compute_type="int8")
        print(f"[model] ready in {time.time() - t0:.1f}s")
        self.recorder = Recorder()

    def _fallback_to_cpu(self):
        """CUDA loads but inference can crash if cublas/cudnn DLLs are missing.
        Rebuild the model on CPU once so dictation keeps working."""
        from faster_whisper import WhisperModel
        print("[model] GPU inference failed; rebuilding on cpu/int8 ...")
        self.model = WhisperModel(self.cfg["model_size"], device="cpu",
                                  compute_type="int8")
        print("[model] cpu model ready")

    def _run_stt(self, audio, prompt):
        try:
            segs, _ = self.model.transcribe(
                audio, language=self.cfg["language"], vad_filter=True,
                beam_size=5, initial_prompt=prompt)
            return " ".join(s.text for s in segs).strip()
        except RuntimeError as e:
            if any(x in str(e).lower() for x in ("cublas", "cudnn", "cuda")):
                self._fallback_to_cpu()
                segs, _ = self.model.transcribe(
                    audio, language=self.cfg["language"], vad_filter=True,
                    beam_size=5, initial_prompt=prompt)
                return " ".join(s.text for s in segs).strip()
            raise

    # --- recording -------------------------------------------------------
    def start(self, mode: str):
        if self.busy:
            return
        self.busy = True
        self.active_mode = mode
        beep(self.cfg, 880)
        self.recorder.start()
        print(f"[rec] {mode}: recording... (release to insert)")

    def stop(self):
        if not self.busy:
            return
        mode = self.active_mode
        audio = self.recorder.stop()
        beep(self.cfg, 440)
        dur = len(audio) / SAMPLE_RATE
        if dur < self.cfg["min_record_seconds"]:
            print(f"[rec] too short ({dur:.2f}s), ignored")
            self.busy = False
            return
        threading.Thread(target=self._process, args=(audio, mode),
                         daemon=True).start()

    # --- transcribe -> (clean|transpile) -> inject -----------------------
    def _process(self, audio, mode: str):
        try:
            prompt = self.cfg["code_initial_prompt"] if mode != "prose" else None
            t0 = time.time()
            raw = self._run_stt(audio, prompt)
            dt = time.time() - t0
            if not raw:
                print(f"[stt] ({dt:.1f}s) no speech")
                return
            print(f'[stt] ({dt:.1f}s) {mode}: "{raw}"')

            if mode == "prose":
                text = clean_text(raw, self.cfg)
                if text:
                    self._inject([("text", text)])
            else:  # python | cpp
                tp = _TRANSPILERS[mode]
                ops = tp.transpile(raw, self.cfg)
                if ops:
                    print(f"[code] {tp.preview(ops)}")
                    self._inject(ops)
        except Exception as e:
            print(f"[error] {e}")
        finally:
            self.busy = False

    def _inject(self, ops):
        import pyperclip
        try:
            old_clip = pyperclip.paste()
        except pyperclip.PyperclipException:
            old_clip = None
        paste_mod = Key.cmd if IS_MAC else Key.ctrl
        delay = self.cfg["key_delay"]

        for kind, val in ops:
            if kind == "text":
                pyperclip.copy(val)
                time.sleep(0.03)
                with self._kbd.pressed(paste_mod):
                    self._kbd.tap("v")
            elif kind == "key":
                if val == "shift_tab":
                    with self._kbd.pressed(Key.shift):
                        self._kbd.tap(Key.tab)
                else:
                    k = _KEY_MAP.get(val)
                    if k is not None:
                        self._kbd.tap(k)
            time.sleep(delay)

        if old_clip is not None:
            threading.Timer(0.6, pyperclip.copy, args=(old_clip,)).start()


def main():
    cfg = load_config()
    app = FlowSuite(cfg)

    bindings = {}
    for hk, mode in cfg["hotkeys"].items():
        try:
            bindings[parse_hotkey(hk)] = mode
        except ValueError as e:
            print(f"[config] {e}")
    held = {"key": None}

    def on_press(key):
        if held["key"] is not None or key not in bindings:
            return
        held["key"] = key
        app.start(bindings[key])

    def on_release(key):
        if key != held["key"]:
            return
        held["key"] = None
        app.stop()

    listener = pynput_keyboard.Listener(on_press=on_press,
                                        on_release=on_release)
    listener.start()

    labels = ", ".join(f"{hk.upper()}={mode}"
                       for hk, mode in cfg["hotkeys"].items())
    print(f"[ready] hold a hotkey: {labels}")
    print("[ready] works in any app, 100% local. Ctrl+C to quit.")
    try:
        listener.join()
    except KeyboardInterrupt:
        pass
    finally:
        listener.stop()
        app.recorder.stream.stop()
        app.recorder.stream.close()
    print("bye")


if __name__ == "__main__":
    sys.exit(main())
