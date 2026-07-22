"""WhisperFlow — private, fully local voice dictation for Windows.

Hold the hotkey (default: F9), speak, release. Your words are transcribed
on-device with faster-whisper and pasted at the cursor in whatever app is
focused. No audio, text, or telemetry ever leaves this machine.
"""

import json
import queue
import re
import sys
import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

try:
    import winsound
except ImportError:
    winsound = None

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
SAMPLE_RATE = 16000

DEFAULT_CONFIG = {
    "hotkey": "f9",
    "mode": "hold",              # "hold" = push-to-talk, "toggle" = press to start/stop
    "model_size": "small",       # tiny/base/small/medium, or distil-small.en etc.
    "device": "cpu",             # "cpu" or "cuda" (see README for GPU setup)
    "compute_type": "int8",      # int8 on cpu, float16 on cuda
    "language": None,            # None = auto-detect, or "en", "hi", ...
    "remove_fillers": True,
    "inject_method": "paste",    # "paste" (fast) or "type" (for apps that block paste)
    "min_record_seconds": 0.3,
    "beep": True,
}

FILLER_RE = re.compile(
    r"\b(um+|uh+|erm+|ah+|hmm+|mm+|mhm+)\b[,.]?\s*", re.IGNORECASE
)


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[config] could not read config.json ({e}), using defaults")
    else:
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
        print(f"[config] wrote default config to {CONFIG_PATH}")
    return cfg


def beep(cfg: dict, freq: int) -> None:
    if cfg["beep"] and winsound is not None:
        threading.Thread(
            target=winsound.Beep, args=(freq, 120), daemon=True
        ).start()


def clean_text(text: str, cfg: dict) -> str:
    text = text.strip()
    if cfg["remove_fillers"]:
        text = FILLER_RE.sub("", text)
        text = re.sub(r"\s{2,}", " ", text)
        text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text.strip()


class Recorder:
    """Keeps the input stream open permanently; buffers audio only while armed."""

    def __init__(self):
        self._chunks: list[np.ndarray] = []
        self._recording = False
        self._lock = threading.Lock()
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=1024,
            callback=self._callback,
        )
        self.stream.start()

    def _callback(self, indata, frames, time_info, status):
        if self._recording:
            with self._lock:
                self._chunks.append(indata.copy())

    def start(self):
        with self._lock:
            self._chunks = []
        self._recording = True

    def stop(self) -> np.ndarray:
        self._recording = False
        with self._lock:
            if not self._chunks:
                return np.zeros(0, dtype=np.float32)
            return np.concatenate(self._chunks).flatten()


class WhisperFlow:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.enabled = True
        self.busy = False
        self.jobs: queue.Queue[np.ndarray] = queue.Queue()

        print(f"[model] loading faster-whisper '{cfg['model_size']}' "
              f"on {cfg['device']} ({cfg['compute_type']}) ...")
        from faster_whisper import WhisperModel
        t0 = time.time()
        try:
            self.model = WhisperModel(
                cfg["model_size"], device=cfg["device"],
                compute_type=cfg["compute_type"],
            )
        except (RuntimeError, ValueError) as e:
            if cfg["device"] != "cpu":
                print(f"[model] {cfg['device']} failed ({e}); falling back to cpu/int8")
                self.model = WhisperModel(
                    cfg["model_size"], device="cpu", compute_type="int8")
            else:
                raise
        print(f"[model] ready in {time.time() - t0:.1f}s")

        self.recorder = Recorder()
        threading.Thread(target=self._worker, daemon=True).start()

    # --- recording control -------------------------------------------------
    def start_recording(self):
        if not self.enabled or self.busy:
            return
        self.busy = True
        beep(self.cfg, 880)
        self.recorder.start()
        print("[rec] recording... (release to transcribe)")

    def stop_recording(self):
        if not self.busy:
            return
        audio = self.recorder.stop()
        beep(self.cfg, 440)
        dur = len(audio) / SAMPLE_RATE
        if dur < self.cfg["min_record_seconds"]:
            print(f"[rec] too short ({dur:.2f}s), ignored")
            self.busy = False
            return
        print(f"[rec] captured {dur:.1f}s, transcribing...")
        self.jobs.put(audio)

    # --- transcription + injection ----------------------------------------
    def _worker(self):
        while True:
            audio = self.jobs.get()
            try:
                t0 = time.time()
                segments, info = self.model.transcribe(
                    audio,
                    language=self.cfg["language"],
                    vad_filter=True,
                    beam_size=5,
                )
                text = " ".join(s.text for s in segments)
                text = clean_text(text, self.cfg)
                dt = time.time() - t0
                if text:
                    print(f'[stt] ({dt:.1f}s, {info.language}) "{text}"')
                    self._inject(text)
                else:
                    print(f"[stt] ({dt:.1f}s) no speech detected")
            except Exception as e:
                print(f"[stt] error: {e}")
            finally:
                self.busy = False

    def _inject(self, text: str):
        import keyboard
        if self.cfg["inject_method"] == "type":
            keyboard.write(text, delay=0.005)
            return
        import pyperclip
        try:
            old_clip = pyperclip.paste()
        except pyperclip.PyperclipException:
            old_clip = None
        pyperclip.copy(text)
        time.sleep(0.05)
        keyboard.send("ctrl+v")
        if old_clip is not None:
            # give the paste time to land before restoring the clipboard
            threading.Timer(0.5, pyperclip.copy, args=(old_clip,)).start()


def make_tray(app: "WhisperFlow"):
    """System tray icon; returns None if pystray is unavailable."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    def draw_icon(color):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([20, 8, 44, 40], radius=12, fill=color)
        d.arc([14, 22, 50, 52], start=0, end=180, fill=color, width=5)
        d.line([32, 52, 32, 60], fill=color, width=5)
        return img

    def toggle(icon, item):
        app.enabled = not app.enabled
        icon.icon = draw_icon("#4caf50" if app.enabled else "#9e9e9e")
        print(f"[tray] dictation {'enabled' if app.enabled else 'paused'}")

    def quit_app(icon, item):
        icon.stop()

    icon = pystray.Icon(
        "WhisperFlow", draw_icon("#4caf50"), "WhisperFlow — local dictation",
        menu=pystray.Menu(
            pystray.MenuItem(
                lambda item: "Pause" if app.enabled else "Resume", toggle),
            pystray.MenuItem("Quit", quit_app),
        ),
    )
    return icon


def main():
    cfg = load_config()
    app = WhisperFlow(cfg)

    import keyboard
    key = cfg["hotkey"]
    if cfg["mode"] == "toggle":
        def on_toggle():
            if app.busy and app.recorder._recording:
                app.stop_recording()
            else:
                app.start_recording()
        keyboard.add_hotkey(key, on_toggle, suppress=True)
        print(f"[ready] press {key.upper()} to start/stop dictation")
    else:
        keyboard.on_press_key(key, lambda e: app.start_recording(), suppress=True)
        keyboard.on_release_key(key, lambda e: app.stop_recording(), suppress=True)
        print(f"[ready] hold {key.upper()} to dictate, release to insert text")
    print("[ready] 100% local - nothing leaves this machine. Ctrl+C to quit.")

    tray = make_tray(app)
    try:
        if tray is not None:
            tray.run()   # blocks until Quit
        else:
            keyboard.wait()
    except KeyboardInterrupt:
        pass
    finally:
        app.recorder.stream.stop()
        app.recorder.stream.close()
    print("bye")


if __name__ == "__main__":
    sys.exit(main())
