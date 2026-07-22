"""Spoken-C++ transpiler — turns loose dictation into C++ source.

Same contract as `spoken_python`: `transpile(text, cfg)` returns an op stream

    ("text", "<c++ fragment>")   ("key", "enter"|"tab"|"shift_tab")

Differences from Python that this handles:
  * statements end in `;`  (auto-appended to non-control lines)
  * blocks use `{ }`      (control headers get a trailing ` {`; say "close brace")
  * logic is `&& || !`    (spoken and/or/not)
  * counted loop template  "for i from 0 to n"  ->  for (int i = 0; i < n; i++) {
  * containers             "vector of int"       ->  vector<int>

Indentation/closing braces are the editor's job: Monaco auto-indents after `{`,
so we never type leading spaces. As in Python, "new line" = Enter,
"dedent" = Shift+Tab.
"""

from __future__ import annotations

import re

# reuse the proven low-level helpers from the Python transpiler
from spoken_python import (
    _NUM_WORDS, _SYMBOL_PHRASES, _apply_pairs, _tidy,
    _DICT_PUNCT_RE, _NEWLINE_RE, _DEDENT_RE, _INDENT_RE, preview,
)

# ---------------------------------------------------------------------------
# Operators — like Python's but logical ops are C++ (&&/||/!) and we add ++/--.
# ORDER MATTERS: compound / multi-word phrases before their prefixes.
# ---------------------------------------------------------------------------
_CPP_OPERATOR_PHRASES: list[tuple[str, str]] = [
    (r"plus equals?", " += "),
    (r"minus equals?", " -= "),
    (r"times equals?", " *= "),
    (r"divided by equals?", " /= "),
    (r"plus plus", "++"),
    (r"minus minus", "--"),
    (r"greater than or equal(?: to)?", " >= "),
    (r"less than or equal(?: to)?", " <= "),
    (r"not equals?(?: to)?", " != "),
    (r"is not equal(?: to)?", " != "),
    (r"(?:is )?equals?(?: to)?", " == "),
    (r"double equals?", " == "),
    (r"greater than", " > "),
    (r"less than", " < "),
    (r"plus", " + "),
    (r"minus", " - "),
    (r"multiplied by", " * "),
    (r"times", " * "),
    (r"integer divided by", " / "),
    (r"divided by", " / "),
    (r"modulo", " % "),
    (r"\bmod\b", " % "),
    (r"to the power of", " pow "),      # no ** in C++; hint, user wraps args
    (r"left shift", " << "),
    (r"right shift", " >> "),
    (r"logical and", " && "),
    (r"logical or", " || "),
    (r"\band\b", " && "),
    (r"\bor\b", " || "),
    (r"\bnot\b", " !"),
    (r"\bgets\b", " = "),
    (r"\bset to\b", " = "),
    (r"\bassign(?:ed)?\b", " = "),
    (r"bitwise and", " & "),
    (r"bitwise or", " | "),
    (r"bitwise xor", " ^ "),
    (r"address of", " & "),
]

# control headers -> wrapped condition + opening brace (no semicolon)
_CPP_STRUCTURE: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^while (.+)$"),   r"while (\1) {"),
    (re.compile(r"^else if (.+)$"), r"else if (\1) {"),
    (re.compile(r"^elif (.+)$"),    r"else if (\1) {"),
    (re.compile(r"^if (.+)$"),      r"if (\1) {"),
    (re.compile(r"^else$"),         r"else {"),
    (re.compile(r"^do$"),           r"do {"),
    (re.compile(r"^switch (.+)$"),  r"switch (\1) {"),
]

# container spoken as "X of Y" -> X<Y>
_CONTAINERS = (r"vector|set|multiset|unordered_set|unordered_map|stack|queue|"
               r"deque|list|priority_queue")


def _cpp_line(line: str, aliases: dict[str, str]) -> str:
    line = line.strip().lower()
    if not line:
        return ""
    for spoken, ident in aliases.items():
        line = re.sub(rf"\b{re.escape(spoken.lower())}\b", ident, line)
    line = re.sub(r"\b[a-z]+\b",
                  lambda m: _NUM_WORDS.get(m.group(0), m.group(0)), line)
    # C++ literal constants (kept lowercase; null -> nullptr)
    for w, c in {"null": "nullptr", "none": "nullptr"}.items():
        line = re.sub(rf"\b{w}\b", c, line)
    # containers / pairs / maps before operators (so "of" survives)
    line = re.sub(rf"\b({_CONTAINERS})\s+of\s+(\w+)", r"\1<\2>", line)
    line = re.sub(r"\bpair of (\w+) (\w+)", r"pair<\1, \2>", line)
    line = re.sub(r"\b(?:unordered_)?map of (\w+) (\w+)", r"map<\1, \2>", line)
    line = re.sub(r"\blength of (\w+)", r"\1.size()", line)
    line = _apply_pairs(line, _CPP_OPERATOR_PHRASES)
    line = _apply_pairs(line, _SYMBOL_PHRASES)
    line = re.sub(r"\s{2,}", " ", line).strip()

    # multi-word STL method names -> snake_case
    for a, b in (("push back", "push_back"), ("pop back", "pop_back"),
                 ("push front", "push_front"), ("pop front", "pop_front"),
                 ("emplace back", "emplace_back")):
        line = re.sub(rf"\b{a}\b", b, line)
    # builtins "F of ..." -> F(...)  (multi-arg, to end of line)
    line = re.sub(r"\b(min|max|abs|sqrt|pow|gcd|lcm|swap|sort|count|find|"
                  r"to_string|stoi|size|make_pair)\s+of\s+(.+)$", r"\1(\2)", line)
    # sentinel constants. "infinity" is unambiguous; "int max"/"int min" only in
    # VALUE position (after = return ( , < > ? :) so a declaration of a variable
    # named max/min isn't clobbered.
    line = re.sub(r"\bnegative infinity\b", "INT_MIN", line)
    line = re.sub(r"\b(?:positive )?infinity\b", "INT_MAX", line)
    line = re.sub(r"(=|return|\(|,|<|>|\?|:)\s*int max\b", r"\1 INT_MAX", line)
    line = re.sub(r"(=|return|\(|,|<|>|\?|:)\s*int min\b", r"\1 INT_MIN", line)
    line = re.sub(r"\blong long max\b", "LLONG_MAX", line)
    line = re.sub(r"\blong long min\b", "LLONG_MIN", line)
    # method calls:  "v . push_back x" -> "v.push_back(x)"
    _M = (r"push_back|pop_back|push_front|pop_front|push|pop|top|front|back|"
          r"begin|end|rbegin|rend|insert|erase|find|count|at|substr|resize|"
          r"assign|emplace_back")
    line = re.sub(rf"\.\s*({_M})\s+(.+)$", r".\1(\2)", line)
    # no-arg methods (NOT first/second — those are attributes)
    line = re.sub(r"\.\s*(size|empty|clear|begin|end|rbegin|rend|top|front|"
                  r"back|pop|pop_back|pop_front)\s*$", r".\1()", line)
    # "X of Y" -> X[Y] indexing (chains "grid of i of j" -> grid[i][j]).
    # For a computed index (i-1) speak brackets instead.
    for _ in range(4):
        nxt = re.sub(r"([a-z_]\w*|\]|\)) of -\s*(\w+)", r"\1[-\2]", line)
        nxt = re.sub(r"([a-z_]\w*|\]|\)) of (\w+)", r"\1[\2]", nxt)
        if nxt == line:
            break
        line = nxt

    # range-for:  "for each x in nums" / "for auto x in nums" -> for (auto& x : nums) {
    m = re.match(r"^for (?:each|auto|every) (\w+) (?:in|of) (.+)$", line)
    if m:
        return f"for (auto& {m.group(1)} : {_tidy(m.group(2))}) {{"
    # counted loop:  for i from 0 to n [step 2]  ->  for (int i = 0; i < n; i++) {
    m = re.match(r"^for (\w+) from (.+?) to (.+?)(?: step (.+))?$", line)
    if m:
        v, a, b, step = m.group(1), m.group(2), m.group(3), m.group(4)
        inc = f"{v} += {step}" if step else f"{v}++"
        return _tidy(f"for (int {v} = {a}; {v} < {b}; {inc}) {{")

    # control headers
    for pat, repl in _CPP_STRUCTURE:
        if pat.match(line):
            return _tidy(pat.sub(repl, line))

    # otherwise it's a statement — auto-append a semicolon
    code = _tidy(line)
    if code and code[-1] not in "{};:" and not code.startswith("#"):
        code += ";"
    return code


def transpile(text: str, cfg: dict | None = None) -> list[tuple[str, str]]:
    """Loose spoken C++ -> op stream. See module docstring."""
    cfg = cfg or {}
    aliases: dict[str, str] = cfg.get("identifier_aliases", {})
    ops: list[tuple[str, str]] = []

    text = _DICT_PUNCT_RE.sub(" ", text)
    marked = _NEWLINE_RE.sub(" \x00 ", text.lower())
    marked = _DEDENT_RE.sub(" \x01 ", marked)
    marked = _INDENT_RE.sub(" \x02 ", marked)

    for tok in re.split(r"(\x00|\x01|\x02)", marked):
        if tok == "\x00":
            ops.append(("key", "enter"))
        elif tok == "\x01":
            ops.append(("key", "shift_tab"))
        elif tok == "\x02":
            ops.append(("key", "tab"))
        else:
            code = _cpp_line(tok, aliases)
            if code:
                ops.append(("text", code))
    return ops


if __name__ == "__main__":
    cfg = {"identifier_aliases": {"d p": "dp", "gnomes": "nums"}}
    samples = [
        "int result gets 0",
        "for i from 0 to n",
        "for i from 0 to n step 2",
        "if gnomes open bracket i close bracket greater than max",
        "while left less than or equal to right",
        "vector of int d p open paren n plus 1 comma 0 close paren",
        "result plus equals gnomes open bracket i close bracket",
        "if x equals to 5 and y greater than 0",
        "return result",
        "close brace",
    ]
    for s in samples:
        print(f"  say : {s}")
        print(f"  code: {preview(transpile(s, cfg))}\n")
