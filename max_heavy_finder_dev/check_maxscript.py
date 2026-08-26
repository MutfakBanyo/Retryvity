#!/usr/bin/env python3
"""Static sanity checks for the Max Heavy Finder MAXScript sources.

MAXScript has no offline interpreter, so this only catches the mechanical
mistakes that break a script at load time: unbalanced brackets, unterminated
strings/comments and unterminated struct/rollout blocks. It is NOT a substitute
for running the tool inside 3ds Max.
"""
import sys

OPEN = {"(": ")", "[": "]", "{": "}"}
CLOSE = {v: k for k, v in OPEN.items()}


def strip_and_check(text, path):
    errors = []
    stack = []          # (char, line)
    i, line, n = 0, 1, len(text)
    state = "code"      # code | string | linecomment | blockcomment
    block_start = string_start = 0
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "\n":
            line += 1
            if state == "linecomment":
                state = "code"
            i += 1
            continue
        if state == "code":
            if c == '"':
                state, string_start = "string", line
            elif c == "-" and nxt == "-":
                state = "linecomment"
                i += 2
                continue
            elif c == "/" and nxt == "*":
                state, block_start = "blockcomment", line
                i += 2
                continue
            elif c in OPEN:
                stack.append((c, line))
            elif c in CLOSE:
                if not stack:
                    errors.append("%s:%d: unexpected '%s'" % (path, line, c))
                elif stack[-1][0] != CLOSE[c]:
                    o, ol = stack[-1]
                    errors.append("%s:%d: '%s' closes '%s' opened at line %d"
                                  % (path, line, c, o, ol))
                    stack.pop()
                else:
                    stack.pop()
        elif state == "string":
            if c == "\\":
                i += 2
                continue
            if c == '"':
                state = "code"
        elif state == "blockcomment":
            if c == "*" and nxt == "/":
                state = "code"
                i += 2
                continue
        i += 1

    if state == "string":
        errors.append("%s:%d: unterminated string literal" % (path, string_start))
    if state == "blockcomment":
        errors.append("%s:%d: unterminated block comment" % (path, block_start))
    for c, ln in stack:
        errors.append("%s:%d: '%s' is never closed" % (path, ln, c))
    return errors


def block_report(text):
    """Rough count of top-level definitions, to spot a truncated file."""
    counts = {"fn ": 0, "struct ": 0, "rollout ": 0, "macroScript ": 0}
    for raw in text.split("\n"):
        s = raw.strip()
        for k in counts:
            if s.startswith(k):
                counts[k] += 1
    return counts


def main(paths):
    failed = False
    for path in paths:
        text = open(path, encoding="utf-8").read()
        errors = strip_and_check(text, path)
        counts = block_report(text)
        print("== %s (%d lines)" % (path, text.count("\n") + 1))
        print("   definitions: %s" % ", ".join("%s%d" % (k.strip(), v) for k, v in counts.items()))
        if errors:
            failed = True
            for e in errors:
                print("   ERROR %s" % e)
        else:
            print("   brackets/strings/comments balanced: OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["MaxHeavyFinder_v0.1.0/MaxHeavyFinder.mcr"]))
