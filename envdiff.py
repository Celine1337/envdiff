#!/usr/bin/env python3
"""envdiff - compare two .env files for configuration drift.

Parses KEY=VALUE lines (blank lines and # comments ignored, optional 'export '
prefix, single/double quoted values, inline comments outside quotes) and
reports three groups: MISSING (key in A not B), EXTRA (key in B not A) and
CHANGED (key in both, different value). Secret-looking values are masked as
**** unless --show-values is given. Single file, standard library only,
no network. Exit codes: 0 no drift, 1 drift found, 2 bad input/path.
"""

import argparse
import json
import os
import re
import sys

__version__ = "1.0.0"

MASK = "****"
SECRET_MARKERS = ("SECRET", "TOKEN", "PASSWORD", "PASSWD", "KEY", "API", "CREDENTIAL")
KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
EXPORT_RE = re.compile(r"^export\s+")
ESCAPES = {"n": "\n", "t": "\t", "r": "\r"}


class EnvError(Exception):
    """Unreadable path or malformed .env input (maps to exit code 2)."""


def is_secret(key):
    """True if the key name contains a secret-looking marker (case-insensitive)."""
    upper = key.upper()
    return any(marker in upper for marker in SECRET_MARKERS)


def parse_value(raw, path, lineno):
    """Parse the text after '=' into a value string."""
    s = raw.strip()
    if not s or s.startswith("#"):
        return ""
    quote = s[0]
    if quote in ("'", '"'):
        out = []
        i = 1
        while i < len(s):
            ch = s[i]
            if quote == '"' and ch == "\\" and i + 1 < len(s):
                nxt = s[i + 1]
                out.append(ESCAPES.get(nxt, nxt))
                i += 2
                continue
            if ch == quote:
                return "".join(out)  # trailing comment/junk after the quote is ignored
            out.append(ch)
            i += 1
        raise EnvError("%s:%d: unterminated %s-quoted value" % (path, lineno, quote))
    m = re.search(r"\s#", s)  # inline comment: '#' preceded by whitespace
    if m:
        s = s[:m.start()]
    return s.rstrip()


def parse_env(text, path="<input>"):
    """Parse .env text into an ordered dict; duplicate keys: last wins."""
    data = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        s = EXPORT_RE.sub("", s, count=1)
        m = KEY_RE.match(s)
        if not m or m.end() == len(s) or s[m.end()] != "=":
            raise EnvError("%s:%d: expected KEY=VALUE, got %r" % (path, lineno, line.strip()))
        data[m.group(0)] = parse_value(s[m.end() + 1:], path, lineno)
    return data


def load_env(path):
    """Read and parse a .env file; raise EnvError if unreadable or malformed."""
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        raise EnvError("cannot read %s: %s" % (path, exc))
    return parse_env(text, path)


def diff(a, b, ignore=()):
    """Compare two parsed env dicts; return {missing, extra, changed}."""
    skip = set(ignore)
    ka, kb = set(a) - skip, set(b) - skip
    return {
        "missing": sorted(ka - kb),
        "extra": sorted(kb - ka),
        "changed": [{"key": k, "old": a[k], "new": b[k]}
                    for k in sorted(ka & kb) if a[k] != b[k]],
    }


def mask_result(result, show_values=False):
    """Copy a diff result, masking secret-looking changed values unless revealed."""
    changed = []
    for c in result["changed"]:
        if not show_values and is_secret(c["key"]):
            changed.append({"key": c["key"], "old": MASK, "new": MASK})
        else:
            changed.append({"key": c["key"], "old": c["old"], "new": c["new"]})
    return {"missing": list(result["missing"]),
            "extra": list(result["extra"]),
            "changed": changed}


def has_drift(result):
    return bool(result["missing"] or result["extra"] or result["changed"])


def colorize(text, color, enabled):
    if not enabled:
        return text
    codes = {"red": "31", "green": "32", "yellow": "33", "bold": "1"}
    return "\x1b[%sm%s\x1b[0m" % (codes[color], text)


def fmt_value(value):
    return value if value else '""'


def report(result, a_name, b_name, color):
    """Human-readable report; values must already be masked as desired."""
    lines = [colorize("%s -> %s" % (a_name, b_name), "bold", color)]
    if not has_drift(result):
        lines.append(colorize("no drift: same keys and values", "green", color))
        return "\n".join(lines)
    if result["missing"]:
        lines.append(colorize("MISSING (%d)" % len(result["missing"]), "red", color))
        lines.extend("  - %s" % k for k in result["missing"])
    if result["extra"]:
        lines.append(colorize("EXTRA (%d)" % len(result["extra"]), "green", color))
        lines.extend("  + %s" % k for k in result["extra"])
    if result["changed"]:
        lines.append(colorize("CHANGED (%d)" % len(result["changed"]), "yellow", color))
        lines.extend("  ~ %s: %s -> %s" % (c["key"], fmt_value(c["old"]), fmt_value(c["new"]))
                     for c in result["changed"])
    return "\n".join(lines)


def want_color(no_color, stream=None):
    stream = sys.stdout if stream is None else stream
    return not no_color and not os.environ.get("NO_COLOR") and stream.isatty()


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="envdiff", description="Compare two .env files for configuration drift.")
    parser.add_argument("a", metavar="A.env", help="baseline .env file")
    parser.add_argument("b", metavar="B.env", help="other .env file")
    parser.add_argument("--ignore", action="append", metavar="KEY[,KEY...]",
                        help="skip these keys (comma-separated, repeatable)")
    parser.add_argument("--show-values", action="store_true",
                        help="reveal secret-looking values instead of " + MASK)
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    parser.add_argument("--version", action="version", version="envdiff " + __version__)
    opts = parser.parse_args(argv)
    ignore = []
    for group in opts.ignore or []:
        ignore.extend(k.strip() for k in group.split(",") if k.strip())
    try:
        a = load_env(opts.a)
        b = load_env(opts.b)
    except EnvError as exc:
        sys.stderr.write("envdiff: %s\n" % exc)
        return 2
    result = mask_result(diff(a, b, ignore), opts.show_values)
    if opts.json:
        print(json.dumps(result, indent=2))
    else:
        print(report(result, opts.a, opts.b, want_color(opts.no_color)))
    return 1 if has_drift(result) else 0


if __name__ == "__main__":
    sys.exit(main())