#!/usr/bin/env python3
"""
patch_zcode.py — Prepend your own system prompt to ZCode.

ZCode's system prompt is assembled at runtime inside the minified bundle
`zcode.cjs`. The very first system section is the "Agent Identity" section,
built by a function that returns an array joined by newlines. This script
injects the contents of your text file as element [0] of that array, so your
prompt is emitted BEFORE everything else the model sees.

Usage
-----
    # Patch using the prompt in system_prompt.txt (default file next to this script)
    python patch_zcode.py

    # Patch using a specific prompt file
    python patch_zcode.py path/to/my_prompt.txt

    # Point at a non-default zcode.cjs (by default the bundle is auto-located
    # under %LOCALAPPDATA%/Programs/ZCode/resources/glm/)
    python patch_zcode.py my_prompt.txt --target "D:/somewhere/zcode.cjs"

    # Undo — restore the pristine original
    python patch_zcode.py --restore

Notes
-----
* Re-running is safe: the script removes its own previous injection and
  re-injects the current file contents. Run it again whenever you edit the
  prompt text.
* The FIRST time it runs it saves a pristine copy as `zcode.cjs.orig`.
  `--restore` copies that back.
* A ZCode app update overwrites zcode.cjs and wipes the patch. Just re-run
  this script after updating. If the update also changes the anchor text,
  the script will refuse to patch (rather than corrupt the file) and tell you.
"""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

DEFAULT_PROMPT = Path(__file__).with_name("system_prompt.txt")


def find_default_target() -> Path:
    """Auto-locate the Windows ZCode install's prompt bundle."""
    local = os.environ.get("LOCALAPPDATA")
    if local:
        cand = Path(local) / "Programs" / "ZCode" / "resources" / "glm" / "zcode.cjs"
        if cand.exists():
            return cand
    return Path("zcode.cjs")  # placeholder; main() reports it missing with a hint


DEFAULT_TARGET = find_default_target()

# Comment markers wrapping our injected element, so we can find and strip a
# previous injection on re-runs. They live OUTSIDE the JS string literal.
MARK_A = "/*ZC_PROMPT_START*/"
MARK_B = "/*ZC_PROMPT_END*/"

# Persona is injected as the CLI-Prefix section content, which ZCode emits as the
# FIRST system message -- ahead of everything, including the identity block. The
# CLI prefix's original text ("You are ZCode...") is replaced by the persona.
# This anchor matches that stable product literal. We rebuild from the pristine
# .orig each run, so injection is always clean/idempotent (no marker-stripping).
CLI_ANCHOR = re.compile(r'"You are ZCode, an interactive coding agent"')


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def restore(target: Path) -> None:
    orig = target.with_suffix(target.suffix + ".orig")
    if not orig.exists():
        die(f"No pristine backup found at {orig} — nothing to restore.")
    shutil.copy2(orig, target)
    print(f"Restored pristine original from {orig.name} -> {target}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Prepend a custom system prompt to ZCode.")
    ap.add_argument(
        "prompt_file",
        nargs="?",
        default=str(DEFAULT_PROMPT),
        help="Text file containing your system prompt (default: system_prompt.txt next to this script).",
    )
    ap.add_argument(
        "--target",
        default=str(DEFAULT_TARGET),
        help="Path to zcode.cjs.",
    )
    ap.add_argument(
        "--restore",
        action="store_true",
        help="Restore the pristine original and exit.",
    )
    args = ap.parse_args()

    target = Path(args.target)
    if not target.exists():
        die(
            f"Target not found: {target}\n"
            "Could not auto-locate the ZCode bundle. Pass it explicitly, e.g.\n"
            '  --target "C:/Users/<you>/AppData/Local/Programs/ZCode/resources/glm/zcode.cjs"'
        )

    if args.restore:
        restore(target)
        return

    prompt_path = Path(args.prompt_file)
    if not prompt_path.exists():
        die(
            f"Prompt file not found: {prompt_path}\n"
            f"Create it (e.g. {DEFAULT_PROMPT}) and put your system prompt inside."
        )

    prompt_text = prompt_path.read_text(encoding="utf-8").rstrip("\n")
    if not prompt_text.strip():
        die(f"Prompt file {prompt_path} is empty.")

    # 1) Save a pristine copy the very first time we ever touch this file.
    orig = target.with_suffix(target.suffix + ".orig")
    if not orig.exists():
        shutil.copy2(target, orig)
        print(f"Saved pristine backup -> {orig.name}")

    # 2) Always keep a rolling backup of the current state before writing.
    shutil.copy2(target, target.with_suffix(target.suffix + ".bak"))

    # 3) Rebuild from the pristine .orig so re-runs are always clean/idempotent.
    #    newline="" keeps the bundle's original line endings byte-exact.
    data = open(orig, "r", encoding="utf-8", newline="").read()

    # 4) Locate the CLI-prefix literal.
    matches = list(CLI_ANCHOR.finditer(data))
    if len(matches) == 0:
        die(
            "Could not find the CLI-prefix anchor. ZCode was probably updated and "
            "its prompt text changed. Re-run with an updated anchor, or ask for help "
            "re-locating it. The file was NOT modified."
        )
    if len(matches) > 1:
        die(f"Anchor matched {len(matches)} times (expected 1); refusing to patch.")

    # 5) Replace the CLI-prefix literal with the persona (as its content), so the
    #    persona becomes the first system message. json.dumps -> proper escaping;
    #    ensure_ascii keeps the bundle ASCII-clean. `*/` inside the prompt is
    #    harmless -- it sits inside a string literal, not a comment.
    literal = json.dumps(prompt_text, ensure_ascii=True)
    injection = f"{MARK_A}{literal}{MARK_B}"
    data = CLI_ANCHOR.sub(lambda m: injection, data, count=1)

    with open(target, "w", encoding="utf-8", newline="") as f:
        f.write(data)

    preview = prompt_text[:200].replace("\n", " ")
    print("\nPatched successfully.")
    print(f"  target : {target}")
    print(f"  prompt : {prompt_path} ({len(prompt_text)} chars)")
    print(f"  preview: {preview}{'...' if len(prompt_text) > 200 else ''}")
    print("\nRestart ZCode for the change to take effect.")
    print("Undo any time with:  python patch_zcode.py --restore")


if __name__ == "__main__":
    main()
