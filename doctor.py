"""FlowSuite doctor - environment self-check.

Run BEFORE (or instead of) launching FlowSuite to confirm your machine is set
up: Python version, required packages, microphone, clipboard, the global-hotkey
backend, and which compute device will be used. It never loads the speech model
and never types anything - it just reports.

    python doctor.py            # or:  python3 doctor.py

Every check prints [ OK ] / [WARN] / [FAIL] with a fix hint. Exit code is
non-zero if anything failed. All imports are lazy so this still runs (and tells
you what's missing) even when dependencies aren't installed yet.
"""

import os
import platform
import sys

_OK = _WARN = _FAIL = 0


def _line(status: str, msg: str, hint: str = "") -> None:
    global _OK, _WARN, _FAIL
    tag = {"OK": "[ OK ]", "WARN": "[WARN]", "FAIL": "[FAIL]"}[status]
    print(f"  {tag} {msg}")
    if hint:
        print(f"         -> {hint}")
    if status == "OK":
        _OK += 1
    elif status == "WARN":
        _WARN += 1
    else:
        _FAIL += 1


def run() -> int:
    system = platform.system()
    print(f"FlowSuite doctor - {system} {platform.release()}, "
          f"Python {platform.python_version()}\n")

    # 1. Python version
    if sys.version_info >= (3, 10):
        _line("OK", f"Python {platform.python_version()}")
    else:
        _line("FAIL", f"Python {platform.python_version()} is too old",
              "install Python 3.10 or newer")

    # 2. required packages
    import importlib
    for mod, pkg in [("faster_whisper", "faster-whisper"),
                     ("sounddevice", "sounddevice"), ("numpy", "numpy"),
                     ("pynput", "pynput"), ("pyperclip", "pyperclip")]:
        try:
            importlib.import_module(mod)
            _line("OK", f"package '{pkg}' importable")
        except Exception as e:
            _line("FAIL", f"package '{pkg}' not importable "
                  f"({e.__class__.__name__})",
                  "pip install -r requirements.txt")

    # 3. microphone (input device present)
    try:
        import sounddevice as sd
        dev = sd.query_devices(kind="input")
        _line("OK", f"microphone available: '{dev['name']}'")
    except Exception as e:
        hint = "check OS microphone permission and that an input device exists"
        if system == "Linux":
            hint = "install PortAudio (e.g. apt install portaudio19-dev)"
        elif system == "Darwin":
            hint = "brew install portaudio; grant Microphone permission"
        _line("FAIL", f"no usable microphone ({e.__class__.__name__})", hint)

    # 4. clipboard (paste-based text injection depends on it)
    try:
        import pyperclip
        token = "__flowsuite_doctor__"
        saved = None
        try:
            saved = pyperclip.paste()
        except Exception:
            pass
        pyperclip.copy(token)
        good = pyperclip.paste() == token
        if saved is not None:
            try:
                pyperclip.copy(saved)
            except Exception:
                pass
        if good:
            _line("OK", "clipboard read/write works")
        else:
            _line("WARN", "clipboard did not round-trip a test value")
    except Exception as e:
        hint = ("install xclip or xsel" if system == "Linux"
                else "check clipboard access for your terminal")
        _line("FAIL", f"clipboard unavailable ({e.__class__.__name__})", hint)

    # 5. global-hotkey backend (pynput listener)
    try:
        from pynput import keyboard as kb
        lis = kb.Listener(on_press=lambda k: None)
        lis.start()
        lis.stop()
        _line("OK", "global hotkey backend works")
    except Exception as e:
        if system == "Linux":
            hint = "use an X11/Xorg session (not Wayland); add user to 'input' group"
        elif system == "Darwin":
            hint = "grant Accessibility permission to your terminal (or python)"
        else:
            hint = "run the terminal as Administrator"
        _line("FAIL", f"hotkey backend failed ({e.__class__.__name__})", hint)

    # 6. compute device that FlowSuite will pick
    try:
        import ctranslate2
        n = ctranslate2.get_cuda_device_count()
        if n > 0:
            _line("OK", f"compute device: NVIDIA GPU detected ({n}) - cuda/float16",
                  "install nvidia-cublas-cu12 nvidia-cudnn-cu12 "
                  "nvidia-cuda-runtime-cu12 to actually use it")
        else:
            _line("OK", "compute device: CPU (cpu/int8)",
                  "no NVIDIA GPU - this is fine; use model_size tiny/base/small")
    except Exception as e:
        _line("WARN", f"could not query compute device ({e.__class__.__name__})")

    # 7. platform-specific reminders
    if system == "Darwin":
        _line("WARN", "macOS: on first real run, grant Microphone + Accessibility "
              "in System Settings > Privacy & Security")
    elif system == "Linux":
        sess = os.environ.get("XDG_SESSION_TYPE", "unknown")
        if sess.lower() == "wayland":
            _line("FAIL", "Wayland session detected",
                  "log into an X11/Xorg session - the hotkey backend needs it")
        else:
            _line("OK", f"session type: {sess}")

    print(f"\nSummary: {_OK} ok, {_WARN} warning(s), {_FAIL} failure(s).")
    if _FAIL:
        print("Fix the [FAIL] items above, then re-run:  python doctor.py")
    else:
        print("Looks good - launch FlowSuite with:  python flowsuite.py")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(run())
