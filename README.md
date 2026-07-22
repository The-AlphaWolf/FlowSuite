# WhisperFlow — private, fully local voice dictation

A Wispr Flow-style dictation tool that runs **entirely on your machine**.
Hold a hotkey, speak, release — your words appear at the cursor in any app
(browser, editor, chat, terminal). No cloud, no account, no telemetry.

## How it mirrors Wispr Flow's architecture (but local)

| Stage            | Wispr Flow (cloud)                  | WhisperFlow (this app)                  |
|------------------|-------------------------------------|-----------------------------------------|
| Trigger          | Hold hotkey                         | Hold `F9` (configurable)                |
| Audio capture    | Local mic → streamed to cloud       | Local mic, stays in RAM                 |
| Speech-to-text   | Proprietary Whisper-class model, cloud GPUs | `faster-whisper` on your CPU/GPU |
| Cleanup          | Cloud LLM removes fillers, fixes punctuation | Local rules: filler removal, spacing, capitalization (Whisper itself handles punctuation) |
| Text delivery    | Injected at cursor via accessibility APIs | Clipboard-paste at cursor (clipboard restored after) |

## Setup

```powershell
pip install -r requirements.txt
python whisperflow.py
```

First run downloads the Whisper model (~460 MB for `small`) from Hugging Face
and caches it locally — that is the **only** network access, ever. After that
it works fully offline. Run as **Administrator** if global hotkeys don't fire
in elevated apps.

## Usage

- **Hold `F9`**, speak, **release** → text is pasted at your cursor.
- High beep = recording started, low beep = stopped.
- Tray icon (green mic): Pause / Resume / Quit.

## Configuration — `config.json` (created on first run)

| Key             | Default   | Notes |
|-----------------|-----------|-------|
| `hotkey`        | `"f9"`    | Any key name the `keyboard` lib accepts |
| `mode`          | `"hold"`  | `"hold"` = push-to-talk, `"toggle"` = press to start/stop |
| `model_size`    | `"small"` | `tiny`/`base` = faster, `medium` = more accurate |
| `device`        | `"cpu"`   | `"cuda"` for GPU (see below) |
| `compute_type`  | `"int8"`  | Use `"float16"` with cuda |
| `language`      | `null`    | Auto-detect; set `"en"` to pin English (faster) |
| `remove_fillers`| `true`    | Strips um/uh/hmm |
| `inject_method` | `"paste"` | `"type"` for apps that block Ctrl+V |

## Optional: GPU acceleration (RTX 3050)

```powershell
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

Then set `"device": "cuda"`, `"compute_type": "float16"` in `config.json`.
If CUDA libs are missing the app automatically falls back to CPU.

## Privacy guarantees

- Audio is held in memory only, never written to disk.
- Inference is on-device (CTranslate2). No API keys, no accounts.
- The only network call is the one-time model download; you can then use it
  fully offline (or copy the `~/.cache/huggingface` folder to an offline box).
