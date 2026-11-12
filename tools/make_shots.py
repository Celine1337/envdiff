#!/usr/bin/env python3
"""Regenerate docs/drift.png and docs/clean.png from real envdiff reports.

Run: python tools/make_shots.py   (requires Pillow)
Tiny .env fixtures are written to a temp dir; the ANSI text is the very
report the CLI prints (colors forced on for the screenshot). Fully offline.
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import envdiff as ed
import render_terminal as rt

A = """\
# production
APP_NAME=demo
HOST=localhost
PORT=8080
API_TOKEN=prod-token-123
LEGACY_FLAG=on
"""

B = """\
# staging
APP_NAME=demo
HOST=0.0.0.0
PORT=8080
API_TOKEN=staging-token-456
NEW_RELIC=off
"""

CLEAN_A = """\
APP_NAME=demo
HOST=localhost
PORT=8080
"""

CLEAN_B = """\
# same pairs: reordered, quoted, export prefix
export PORT=8080
HOST=localhost
APP_NAME="demo"
"""


def render(name, ansi, cmd, title):
    rt.render(rt.parse_ansi(ansi), title, cmd, os.path.join(ROOT, "docs", name + ".png"))


def shot(tmp, name, left, right, a_label, b_label, cmd, title):
    a_path = os.path.join(tmp, name + "-a.env")
    b_path = os.path.join(tmp, name + "-b.env")
    with open(a_path, "w", encoding="utf-8") as fh:
        fh.write(left)
    with open(b_path, "w", encoding="utf-8") as fh:
        fh.write(right)
    result = ed.mask_result(ed.diff(ed.load_env(a_path), ed.load_env(b_path)))
    ansi = ed.report(result, a_label, b_label, True)
    render(name, ansi, cmd, title)


def main():
    os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        shot(tmp, "drift", A, B, "a.env", "b.env",
             "python envdiff.py a.env b.env", "envdiff — drift")
        shot(tmp, "clean", CLEAN_A, CLEAN_B, "a.env", "a-copy.env",
             "python envdiff.py a.env a-copy.env", "envdiff — clean")


if __name__ == "__main__":
    main()