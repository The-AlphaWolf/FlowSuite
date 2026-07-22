# FlowSuite — one local voice engine, three hotkeys

Unifies **prose dictation** and **voice coding** into a single always-on,
fully on-device process. One shared whisper model, one microphone stream.
Push-to-talk; text is injected at the cursor in **any** app (browser editor,
VS Code, Word, terminal). No cloud, no account, no telemetry.

| Hold | Mode | What it does |
|------|------|--------------|
| **F10** | prose  | Natural dictation — fillers stripped, capitalized (Wispr-Flow-style) |
| **F8**  | python | Spoken Python → real syntax via `spoken_python` |
| **F9**  | cpp    | Spoken C++ → real syntax via `spoken_cpp` |

Release to insert. High beep = recording, low beep = inserted.

## Run

```bash
pip install -r requirements.txt
python flowsuite.py
```

Or double-click `run_flowsuite.bat`. First run writes `flowsuite_config.json`.

- GPU (RTX 3050) is used automatically; falls back to CPU/int8 if CUDA libs
  are missing.
- Runs in any focused app — injection is clipboard-paste + keystrokes, global.

### Autostart at login

`start_flowsuite.vbs` (copied into `shell:startup`) launches FlowSuite hidden
on every boot. To (re)install manually: copy it into the folder shown by
`Win+R → shell:startup`.

## How it works

```
hold hotkey → mic → faster-whisper → clean_text | transpile → keystrokes at cursor
```

- **Prose:** `whisperflow.clean_text` strips um/uh, fixes spacing, capitalizes.
- **Code:** the mode's transpiler (`spoken_python` / `spoken_cpp`) rewrites loose
  speech into syntax deterministically — no LLM.
- **Indentation is the editor's job.** LeetCode's Monaco auto-indents after `:`
  (Python) or `{` (C++), so FlowSuite never types leading spaces. Say
  **"dedent"** (Shift+Tab) to leave a block, **"new line"** for Enter.

## GPU note (baked in)

faster-whisper/ctranslate2 loads `cublas64_12.dll` / `cudnn64_9.dll` by **bare
name**, which Windows resolves via `PATH` only. FlowSuite's `_enable_cuda_dlls()`
prepends the `nvidia-*-cu12` wheel bin dirs to `PATH` at startup, so GPU works
without a system CUDA install. Required wheels:

```bash
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 nvidia-cuda-runtime-cu12
```

## Dictation cheat-sheets

### Shared structure commands (code modes)
`new line` = Enter · `dedent` = leave block (Shift+Tab) · `indent` = extra Tab
Brackets: `open/close paren` `( )` · `open/close bracket` `[ ]` · `open/close brace` `{ }`
Say `comma` `colon` `dot` for literal punctuation.

### Python (F8)
| Say | Get |
|-----|-----|
| for i in range n / range of n | `for i in range(n):` |
| for x in nums | `for x in nums:` |
| if x greater than y | `if x > y:` |
| while left less than or equal to right | `while left <= right:` |
| dp of i gets dp of i minus 1 plus 1 *(use brackets: "dp open bracket i close bracket")* | `dp[i] = dp[i - 1] + 1` |
| res gets max of res comma current | `res = max(res, current)` |
| min/max/len/sum/sorted/abs **of** … | `min(…)`, `len(…)`, … |
| nums dot append i | `nums.append(i)` |
| stack dot pop / count dot get key comma 0 | `stack.pop()` / `count.get(key, 0)` |
| negative infinity | `float('-inf')` |
| x not in seen / a if x greater than 0 else b | membership / ternary pass through |

Constants: `true`/`false`/`none` → `True`/`False`/`None`.

### C++ (F9)
| Say | Get |
|-----|-----|
| int result gets 0 | `int result = 0;` *(auto `;`)* |
| for i from 0 to n | `for (int i = 0; i < n; i++) {` |
| for i from 0 to n step 2 | `for (int i = 0; i < n; i += 2) {` |
| for each x in nums | `for (auto& x : nums) {` |
| vector of int dp open paren n plus 1 comma 0 close paren | `vector<int> dp(n + 1, 0);` |
| if x equals to 5 and y greater than 0 | `if (x == 5 && y > 0) {` |
| nums dot push back x / dot size / dot pop | `nums.push_back(x)` / `.size()` / `.pop()` |
| max/min/abs **of** … | `max(…)`, … |
| int max / int min / infinity | `INT_MAX` / `INT_MIN` |
| return result | `return result;` |
| close brace | `}` |

C++ rules: statements auto-get `;`; control headers auto-get ` {`;
and→`&&`, or→`||`, not→`!`; `push back`→`push_back`; container "X of Y" → `X<Y>`.

## Config — `flowsuite_config.json`

| Key | Default | Notes |
|-----|---------|-------|
| `hotkeys` | `{"f10":"prose","f8":"python","f9":"cpp"}` | hotkey → mode |
| `model_size` | `"small"` | `medium` = more accurate, slower |
| `device` / `compute_type` | `"cuda"` / `"float16"` | auto-falls back to `cpu`/`int8` |
| `code_initial_prompt` | code-biased vocab | nudges whisper toward code tokens |
| `identifier_aliases` | `{"d p":"dp", …}` | fix words whisper mishears → real names |
| `remove_fillers` | `true` | prose mode: strip um/uh |
| `key_delay` | `0.02` | pause between injected ops |

## Known limits (rule-based, by design)

- Only phrases in the tables map; unknown loose speech inserts near-verbatim —
  add rows to `spoken_python.py` / `spoken_cpp.py` when you hit a gap.
- Whisper mishears short identifiers (`dp`, `idx`, `nums`). Fight it with
  `identifier_aliases` + `code_initial_prompt`. Watch `flowsuite.log`'s `[stt]`
  line for what it actually heard.
- Operator precedence is literal — parenthesize by voice when it matters.

## Files

- `flowsuite.py` — unified engine (hotkeys, model, injection)
- `spoken_python.py` / `spoken_cpp.py` — transpilers (`transpile(text, cfg) → ops`)
- `whisperflow.py` — shared audio capture + prose `clean_text` (also runs standalone)
- `start_flowsuite.vbs` / `run_flowsuite.bat` — autostart / manual launch
- `flowsuite.log` — runtime log

Each transpiler has a built-in smoke test: `python spoken_python.py`.

---

## Standalone WhisperFlow (prose-only, cross-platform)

`whisperflow.py` is the original prose-dictation tool and the shared library
FlowSuite is built on. It runs on its own on **Windows, macOS, and Linux (X11)**
if you only want dictation (no code modes):

```bash
python whisperflow.py        # hold F9 (its own default), speak, release
```

- **macOS:** `brew install portaudio` first; grant **Accessibility** +
  **Microphone** permission to your terminal on first run.
- **Linux:** X11 only (the `pynput` backend doesn't support Wayland);
  `sudo apt install portaudio19-dev xclip`, and add your user to the `input`
  group if the hotkey doesn't register.

### Privacy guarantees (both tools)

- Audio is held in memory only, never written to disk.
- Inference is on-device (CTranslate2). No API keys, no accounts.
- The only network call is the one-time whisper model download (~460 MB for
  `small`); after that it runs fully offline.
