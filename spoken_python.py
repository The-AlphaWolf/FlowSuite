"""Spoken-Python transpiler — turns loose dictation into Python source.

`transpile(text, cfg)` returns an **op stream** the injector replays:

    ("text", "<python fragment>")   # paste/type verbatim at the cursor
    ("key",  "enter")               # newline  (editor then auto-indents)
    ("key",  "tab")                 # manual extra indent
    ("key",  "shift_tab")           # dedent / exit a block

Indentation is deliberately left to the code editor. LeetCode's Monaco editor
auto-indents the line after any line ending in ``:``, so we never prepend
spaces ourselves — we only emit Enter and, on the "dedent" command, Shift+Tab.

The whole pipeline is deterministic string rewriting: no model, no network.
It is meant to be *extended* — add rows to the tables below as you discover
phrases you say that don't map yet.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# 0. Number words -> digits  (whisper often already emits digits, this is backup)
# ---------------------------------------------------------------------------
_NUM_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20", "hundred": "100",
    "thousand": "1000",
}

# ---------------------------------------------------------------------------
# 1. Multi-word operator / comparison phrases -> symbols.
#    ORDER MATTERS: longest / most specific phrases first so "greater than or
#    equal to" wins over "greater than". Applied as whole-word regex on the
#    lowercased, space-joined utterance.
# ---------------------------------------------------------------------------
_OPERATOR_PHRASES: list[tuple[str, str]] = [
    # compound assignment
    (r"plus equals?", " += "),
    (r"minus equals?", " -= "),
    (r"times equals?", " *= "),
    (r"divided by equals?", " /= "),
    # comparison (specific before general)
    (r"greater than or equal(?: to)?", " >= "),
    (r"less than or equal(?: to)?", " <= "),
    (r"not equals?(?: to)?", " != "),
    (r"is not equal(?: to)?", " != "),
    (r"(?:is )?equals?(?: to)?", " == "),
    (r"double equals?", " == "),
    (r"greater than", " > "),
    (r"less than", " < "),
    # arithmetic
    (r"plus", " + "),
    (r"minus", " - "),
    (r"multiplied by", " * "),
    (r"times", " * "),
    (r"integer divided by", " // "),
    (r"floor divided by", " // "),
    (r"divided by", " / "),
    (r"modulo", " % "),
    (r"\bmod\b", " % "),
    (r"to the power of", " ** "),
    (r"\bpower\b", " ** "),
    # assignment (spoken)  — after == so "equals" already consumed
    (r"\bgets\b", " = "),
    (r"\bset to\b", " = "),
    (r"\bassign(?:ed)?\b", " = "),
    # bitwise / boolean spoken forms kept as python keywords where natural
    (r"bitwise and", " & "),
    (r"bitwise or", " | "),
    (r"bitwise xor", " ^ "),
    (r"left shift", " << "),
    (r"right shift", " >> "),
]

# ---------------------------------------------------------------------------
# 2. Symbol / punctuation words -> characters (spoken explicitly).
# ---------------------------------------------------------------------------
_SYMBOL_PHRASES: list[tuple[str, str]] = [
    (r"open paren(?:thesis)?", " ( "),
    (r"close paren(?:thesis)?", " ) "),
    (r"open (?:square )?bracket", " [ "),
    (r"close (?:square )?bracket", " ] "),
    (r"open (?:curly )?brace", " { "),
    (r"close (?:curly )?brace", " } "),
    (r"\bcomma\b", " , "),
    (r"\bcolon\b", " : "),
    (r"semicolon", " ; "),
    (r"\bdot\b", " . "),
    (r"\bperiod\b", " . "),
    (r"underscore", "_"),
    (r"arrow", " -> "),
    (r"double quote", '"'),
    (r"single quote", "'"),
    (r"\bquote\b", '"'),
]

# ---------------------------------------------------------------------------
# 3. Structural templates. Applied to a single logical line AFTER operators &
#    symbols are converted. Each adds parentheses / trailing colon so the
#    editor's auto-indent kicks in.
#    Regexes run on the space-normalized line; capture groups are the payload.
# ---------------------------------------------------------------------------
_STRUCTURE_RULES: list[tuple[re.Pattern, str]] = [
    # for i in range n           -> for i in range(n):
    # for i in range n comma m   -> for i in range(n, m):   (comma already ',')
    (re.compile(r"^for (\w+) in range (.+)$"),        r"for \1 in range(\2):"),
    # for x in nums              -> for x in nums:
    (re.compile(r"^for (\w+) in (.+)$"),              r"for \1 in \2:"),
    (re.compile(r"^while (.+)$"),                     r"while \1:"),
    (re.compile(r"^else if (.+)$"),                   r"elif \1:"),
    (re.compile(r"^elif (.+)$"),                      r"elif \1:"),
    (re.compile(r"^if (.+)$"),                        r"if \1:"),
    (re.compile(r"^else$"),                           r"else:"),
    (re.compile(r"^try$"),                            r"try:"),
    (re.compile(r"^except(?: (.+))?$"),               r"except \1:"),
    (re.compile(r"^finally$"),                        r"finally:"),
    (re.compile(r"^class (\w+)(?: (.+))?$"),          r"class \1\2:"),
    # print x         -> print(x)
    (re.compile(r"^print (.+)$"),                     r"print(\1)"),
    (re.compile(r"^append (.+)$"),                    r".append(\1)"),
    (re.compile(r"^return$"),                         r"return"),
]

# ---------------------------------------------------------------------------
# 4. Line-splitting / indentation commands -> key ops.
# ---------------------------------------------------------------------------
_NEWLINE_RE = re.compile(r"\b(?:new ?line|next line|end line)\b")
_DEDENT_RE = re.compile(r"\b(?:dedent|de indent|un ?indent|outdent|end block|"
                        r"exit block)\b")
_INDENT_RE = re.compile(r"\b(?:indent|tab in)\b")

# tidy spacing around these once code-ish
_TIGHT_LEFT = set(")],:.;")     # no space before
_TIGHT_RIGHT = set("([.")       # no space after


def _apply_pairs(text: str, pairs: list[tuple[str, str]]) -> str:
    for pat, repl in pairs:
        text = re.sub(pat, repl, text)
    return text


def _tidy(code: str) -> str:
    """Collapse the spaces the phrase tables sprinkled in, into real code."""
    code = re.sub(r"\s+", " ", code).strip()
    # remove space before tight-left punctuation:  "dp [ i ]" -> "dp[ i ]"
    code = re.sub(r"\s+([)\]\},:;.])", r"\1", code)
    # remove space after tight-right punctuation:  "dp[ i" -> "dp[i"
    code = re.sub(r"([(\[.])\s+", r"\1", code)
    # tighten call / index brackets:  "dp [i]" -> "dp[i]",  "f (x)" -> "f(x)"
    code = re.sub(r"(\w|\)|\])\s+([(\[])", r"\1\2", code)
    # ...but keep a space after keywords: "while(x)" -> "while (x)" (not a call)
    code = re.sub(r"\b(if|elif|while|for|return|in|and|or|not|else|assert|"
                  r"yield|del|raise|lambda|import|from|as)([(\[])", r"\1 \2", code)
    # normalize spaces around binary operators (already padded, just single)
    code = re.sub(r"\s*(==|!=|<=|>=|//|\*\*|\+=|-=|\*=|/=|<<|>>|->)\s*",
                  r" \1 ", code)
    # comma always "x, y"
    code = re.sub(r"\s*,\s*", ", ", code)
    code = re.sub(r"\s{2,}", " ", code)
    return code.strip()


def _transpile_line(line: str, aliases: dict[str, str]) -> str:
    line = line.strip().lower()
    if not line:
        return ""
    # identifier aliases (fix whisper mangling: "gnomes" -> "nums")
    for spoken, ident in aliases.items():
        line = re.sub(rf"\b{re.escape(spoken.lower())}\b", ident, line)
    # number words -> digits (word-boundary, skip if already digit-ish)
    line = re.sub(r"\b[a-z]+\b",
                  lambda m: _NUM_WORDS.get(m.group(0), m.group(0)), line)
    # python literal constants (spoken lowercase -> capitalized)
    for word, const in {"true": "True", "false": "False",
                        "none": "None", "null": "None"}.items():
        line = re.sub(rf"\b{word}\b", const, line)
    # operators, then symbols
    line = _apply_pairs(line, _OPERATOR_PHRASES)
    line = _apply_pairs(line, _SYMBOL_PHRASES)
    line = re.sub(r"\s{2,}", " ", line).strip()
    # common phrasings: "in range of n" -> "in range n", "length of x"->"len(x)"
    line = re.sub(r"\bin range of\b", "in range", line)
    line = re.sub(r"\blength of (\w+)", r"len(\1)", line)
    # builtins spoken as "F of ..." -> F(...).  Capture to end so multi-arg /
    # bracketed forms work: "max of a comma b" -> max(a, b) (comma already ",").
    line = re.sub(r"\b(len|sum|min|max|sorted|reversed|abs|set|list|tuple|"
                  r"str|int|float|bool|enumerate|any|all)\s+of\s+(.+)$",
                  r"\1(\2)", line)
    line = re.sub(r"\babsolute value of (.+)$", r"abs(\1)", line)
    # infinities (very common in DP / min-max init)
    line = re.sub(r"\bnegative infinity\b", "float('-inf')", line)
    line = re.sub(r"\b(?:positive )?infinity\b", "float('inf')", line)
    # method calls:  "nums . append x" -> "nums.append(x)",  ". keys" -> ".keys()"
    _METHODS = (r"append|appendleft|add|pop|popleft|remove|insert|get|count|"
                r"index|sort|reverse|extend|update|discard|split|join|strip|"
                r"lower|upper|keys|values|items|find|replace|startswith|"
                r"endswith|most_common")
    line = re.sub(rf"\.\s*({_METHODS})\s+(.+)$", r".\1(\2)", line)
    line = re.sub(rf"\.\s*({_METHODS})\s*$", r".\1()", line)
    # define function two sum with nums comma target -> def two_sum(nums, target):
    m = re.match(r"^def(?:ine)? (?:function |method )?(.+?)(?: with (.+))?$", line)
    if m:
        name = re.sub(r"\s+", "_", m.group(1).strip())
        params = _tidy(m.group(2)) if m.group(2) else ""
        return f"def {name}({params}):"
    # structural templates (first match wins)
    for pat, repl in _STRUCTURE_RULES:
        m = pat.match(line)
        if m:
            line = pat.sub(repl, line)
            break
    return _tidy(line)


# whisper sprinkles prose punctuation (", . ; ! ?") into dictated code — strip
# it up front. Real punctuation is spoken as words ("comma", "colon", "dot")
# and re-added later, so nothing is lost.
_DICT_PUNCT_RE = re.compile(r"[,.;!?]+")


def transpile(text: str, cfg: dict | None = None) -> list[tuple[str, str]]:
    """Loose spoken Python -> op stream. See module docstring."""
    cfg = cfg or {}
    aliases: dict[str, str] = cfg.get("identifier_aliases", {})
    ops: list[tuple[str, str]] = []

    text = _DICT_PUNCT_RE.sub(" ", text)

    # 1) carve the utterance into segments on spoken newline commands, keeping
    #    dedent/indent commands as their own segments.
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
            code = _transpile_line(tok, aliases)
            if code:
                ops.append(("text", code))
    return ops


def preview(ops: list[tuple[str, str]]) -> str:
    """Human-readable one-liner for logging what will be injected."""
    out = []
    for kind, val in ops:
        if kind == "text":
            out.append(val)
        elif val == "enter":
            out.append("<NL>")
        elif val == "shift_tab":
            out.append("<DEDENT>")
        elif val == "tab":
            out.append("<INDENT>")
    return " ".join(out)


if __name__ == "__main__":
    # quick manual smoke test
    cfg = {"identifier_aliases": {"d p": "dp", "gnomes": "nums"}}
    samples = [
        "for i in range n",
        "if x greater than y",
        "d p open bracket i close bracket gets d p open bracket i minus one "
        "close bracket plus one",
        "while left less than or equal to right",
        "res plus equals gnomes open bracket i close bracket",
        "define function two sum with nums comma target",
        "if i greater than zero new line return result",
        "return left plus right divided by two",
    ]
    for s in samples:
        print(f"  say : {s}")
        print(f"  code: {preview(transpile(s, cfg))}\n")
