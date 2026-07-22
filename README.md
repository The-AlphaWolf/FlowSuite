# FlowSuite — one local voice engine, three hotkeys

Turn your voice into **prose** *and* **code**, entirely on your own machine.
Hold a hotkey, speak, release — the text appears at your cursor in **any** app
(browser code editor, VS Code, Word, terminal). No cloud, no account, no
telemetry, no data ever leaves your computer.

| Hold | Mode | What it does |
|------|------|--------------|
| **F10** | prose  | Natural dictation — fillers stripped, capitalized |
| **F8**  | python | Spoken Python → real syntax (e.g. "for i in range n" → `for i in range(n):`) |
| **F9**  | cpp    | Spoken C++ → real syntax (e.g. "for i from 0 to n" → `for (int i = 0; i < n; i++) {`) |

Runs on **Windows, macOS, and Linux**. Uses your GPU if you have an NVIDIA one,
otherwise runs on the CPU — **no GPU is required.**

---

## Quick start

```bash
git clone https://github.com/The-AlphaWolf/FlowSuite.git
cd FlowSuite
pip install -r requirements.txt
python doctor.py           # verify mic, clipboard, hotkeys, GPU/CPU (recommended)
python flowsuite.py        # Windows;  use  python3 flowsuite.py  on macOS/Linux
```

> Run **`python doctor.py`** any time you hit trouble — it checks every
> dependency and permission and tells you exactly what to fix, per platform.

On first run it downloads the speech model (~460 MB for `small`) once, prints
`[ready]`, then listens. Hold **F8** in a code editor and say
"for i in range n". That's it.

> **Heads-up:** most systems need one small OS-level dependency first
> (PortAudio for the mic, and on Linux a clipboard tool). See your platform
> below.

---

## Requirements

- **Python 3.10 or newer**
- A microphone
- ~1–2 GB free disk for the model cache
- Optional: an **NVIDIA GPU** for faster transcription (see
  [GPU acceleration](#gpu-acceleration-optional)). Everything works on CPU
  without it.

The Python packages (installed by `pip install -r requirements.txt`):
`faster-whisper`, `sounddevice`, `numpy`, `pynput`, `pyperclip`, `pystray`,
`Pillow`.

---

## Install per platform

### Windows

```powershell
pip install -r requirements.txt
python flowsuite.py
```

- If global hotkeys don't fire inside an elevated app, run your terminal
  **as Administrator**.
- `sounddevice` ships PortAudio on Windows — nothing extra to install.

### macOS

```bash
brew install portaudio          # microphone backend for sounddevice
pip3 install -r requirements.txt
python3 flowsuite.py
```

- The **first time**, macOS will prompt for **Microphone** and **Accessibility**
  permission (Accessibility is needed to send the hotkey/paste). Grant both to
  your terminal app (or to `python3`) under
  **System Settings → Privacy & Security**.
- Apple-Silicon and Intel Macs run on the **CPU** (no NVIDIA CUDA on macOS).
  The `small` model is comfortably fast on Apple Silicon.

### Linux

```bash
# Debian/Ubuntu (use your distro's equivalents elsewhere)
sudo apt install portaudio19-dev xclip
pip3 install -r requirements.txt
python3 flowsuite.py
```

- **X11 sessions only.** The hotkey/paste backend (`pynput`) does not support
  Wayland. On recent GNOME/Fedora/Ubuntu, log into an "Ubuntu on Xorg" / X11
  session instead.
- `xclip` (or `xsel`) is required for clipboard paste — install one.
- If the hotkey doesn't register, add your user to the `input` group
  (`sudo usermod -aG input $USER`, then log out/in).

---

## GPU acceleration (optional)

FlowSuite auto-detects your hardware: `device: "auto"` in the config uses an
**NVIDIA GPU if one is present**, otherwise the CPU. You don't have to configure
anything.

To actually use an NVIDIA GPU you need the CUDA runtime libraries. The easiest
way is via pip wheels (no system CUDA install required):

```bash
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 nvidia-cuda-runtime-cu12
```

- **Windows:** FlowSuite adds these wheels' folders to the DLL search path
  automatically — nothing else to do.
- **Linux:** you may also need
  `export LD_LIBRARY_PATH=$(python3 -c "import os,nvidia;print(':'.join(os.path.join(p,'lib') for p in __import__('glob').glob(os.path.dirname(nvidia.__file__)+'/*')))")`
  before launching, or install your distro's CUDA/cuDNN packages.
- **macOS / no NVIDIA GPU / AMD / Intel:** ignore all of the above — FlowSuite
  runs on the CPU, which is plenty for short dictation.

Force a specific backend by editing `flowsuite_config.json`:
`"device": "cpu"` (+ `"compute_type": "int8"`) or
`"device": "cuda"` (+ `"compute_type": "float16"`).

---

## Model size vs. speed & accuracy

Set `"model_size"` in `flowsuite_config.json`. Larger = more accurate, slower,
more memory. First use of a size downloads it once.

| Size | Rough VRAM/RAM | Notes |
|------|----------------|-------|
| `tiny` / `base` | small | fastest, least accurate — fine on slow CPUs |
| `small` (default) | ~0.5 GB | good balance; recommended |
| `medium` | ~2 GB | more accurate, noticeably slower on CPU |
| `large-v3` | ~4 GB+ | best accuracy; realistically GPU-only |

CPU-only machine? Stick to `tiny`/`base`/`small`.

---

## Autostart at login (optional)

**Windows** — copy `start_flowsuite.vbs` into the folder that opens with
`Win+R → shell:startup`. It launches FlowSuite hidden on every boot.

**macOS**
```bash
bash macos/install_autostart.sh
```

**Linux (desktop session)**
```bash
bash linux/install_autostart.sh
```
(The script also prints a systemd-user alternative for headless setups.)

---

## How it works

```
hold hotkey → mic → faster-whisper → clean_text | transpile → keystrokes at cursor
```

- **Prose** strips um/uh, fixes spacing, capitalizes.
- **Code** runs a deterministic rule-based transpiler (`spoken_python.py` /
  `spoken_cpp.py`) — **no LLM**, nothing to train, fully offline.
- **Indentation is the editor's job.** Code editors auto-indent after `:`
  (Python) or `{` (C++), so FlowSuite never types leading spaces. Say
  **"new line"** for Enter, **"dedent"** to leave a block.

---

## Dictation cheat-sheets

### Structure commands (code modes)
`new line` = Enter · `dedent` = leave block · `indent` = extra indent
Brackets: `open/close paren` `( )` · `open/close bracket` `[ ]` · `open/close brace` `{ }`
Say `comma` `colon` `dot` for literal punctuation.

### Python (F8)
| Say | Get |
|-----|-----|
| for i in range n / range of n | `for i in range(n):` |
| for i in range 1 to n | `for i in range(1, n):` |
| for x in nums | `for x in nums:` |
| if x greater than y and y less than z | `if x > y and y < z:` |
| dp of i | `dp[i]`  ·  grid of i of j → `grid[i][j]` |
| dp of i gets max of dp of i comma nums of i | `dp[i] = max(dp[i], nums[i])` |
| nums dot append i / stack dot pop | `nums.append(i)` / `stack.pop()` |
| len/sum/min/max/sorted **of** … | `len(…)`, `min(…)`, … |
| negative infinity | `float('-inf')` |
| x not in seen · a if x greater than 0 else b | membership / ternary |

Constants: `true`/`false`/`none` → `True`/`False`/`None`.

### C++ (F9)
| Say | Get |
|-----|-----|
| int result gets 0 | `int result = 0;` *(auto `;`)* |
| for i from 0 to n | `for (int i = 0; i < n; i++) {` |
| for each x in nums | `for (auto& x : nums) {` |
| vector of int dp open paren n comma 0 close paren | `vector<int> dp(n, 0);` |
| if x equals to 5 and y greater than 0 | `if (x == 5 && y > 0) {` |
| nums dot push back x / dot size | `nums.push_back(x)` / `.size()` |
| dp of i / grid of i of j | `dp[i]` / `grid[i][j]` |
| ans gets int max | `ans = INT_MAX;` |
| return result / close brace | `return result;` / `}` |

Logic: and→`&&`, or→`||`, not→`!`. Statements auto-get `;`; control headers auto-get ` {`.

**Tip — computed indices:** "dp of i minus 1" gives `dp[i] - 1`. For `dp[i - 1]`
speak the brackets: "dp open bracket i minus 1 close bracket".

---

## Configuration — `flowsuite_config.json`

Created on first run; per-machine, not tracked by git.

| Key | Default | Notes |
|-----|---------|-------|
| `hotkeys` | `{"f10":"prose","f8":"python","f9":"cpp"}` | hotkey → mode |
| `model_size` | `"small"` | see table above |
| `device` / `compute_type` | `"auto"` / `"auto"` | GPU if present, else CPU |
| `language` | `"en"` | pin a language, or `null` to auto-detect |
| `code_initial_prompt` | code vocab | biases whisper toward code tokens |
| `identifier_aliases` | `{"d p":"dp", …}` | fix words whisper mishears |
| `key_delay` | `0.02` | pause between injected keystrokes |

---

## Troubleshooting

**First, run `python doctor.py`** — it verifies Python, packages, microphone,
clipboard, hotkey backend, and compute device, and prints a fix hint for each
failure. Common issues:

- **Nothing is inserted, no beep** — the hotkey isn't reaching the app. On macOS
  grant Accessibility permission; on Linux use an X11 session / join the `input`
  group; on Windows run the terminal as Administrator.
- **Beeps but nothing appears** — check the console/`flowsuite.log`. A CUDA error
  means the GPU libs are missing → it auto-falls back to CPU (or set
  `"device": "cpu"`).
- **Paste does nothing on Linux** — install `xclip` or `xsel`.
- **Wrong words for short identifiers** (`dp` heard as "d p") — add them to
  `identifier_aliases` in `flowsuite_config.json`. The `[stt]` line in the log
  shows exactly what was heard.
- **Hotkey conflicts** with an app — change `hotkeys` in the config to other
  F-keys.

---

## Privacy

- Audio is held in memory only, never written to disk.
- Inference is 100% on-device (CTranslate2). No API keys, no accounts.
- The only network access is the one-time model download; after that FlowSuite
  works fully offline.

---

## Files

- `flowsuite.py` — the app (hotkeys, model, text injection)
- `spoken_python.py` / `spoken_cpp.py` — transpilers (`transpile(text, cfg) → ops`)
- `whisperflow.py` — shared mic capture + prose `clean_text`
- `doctor.py` — environment self-check (`python doctor.py`)
- `run_flowsuite.bat` (Windows) / `run_flowsuite.sh` (macOS/Linux) — launchers
- `start_flowsuite.vbs`, `macos/`, `linux/` — autostart helpers per OS

Extending the code vocabulary: add rows to the phrase tables in
`spoken_python.py` / `spoken_cpp.py`, then run `python spoken_python.py` for the
built-in smoke test.

---

## Standalone WhisperFlow (prose-only)

`whisperflow.py` is the original prose-dictation tool and the shared library
FlowSuite builds on. If you only want dictation (no code modes) it runs on its
own — `python whisperflow.py` (default hotkey F9), same platform notes as above.
