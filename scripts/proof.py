#!/usr/bin/env python3
"""Check a plan's graphics before rendering: one proof image and a list of warnings.

Draws every graphic once, as it will look, into a single sheet (out/<name>/work/proof.jpg),
and runs the automatic tests: text squeezed too small, content running into a card's edge,
a graphic sitting on the speaker's head, a graphic on screen too briefly. Takes seconds and needs no
rendered video. Look at the sheet, fix what the warnings and your eyes find, then render.

Usage: reel proof out/<name>/plan.json
"""

import sys

import graphics
import kit


def main():
    plan_path, plan = kit.load_plan(sys.argv[1])
    work = plan_path.parent / "work"
    work.mkdir(parents=True, exist_ok=True)
    sheet = work / "proof.jpg"
    warnings = graphics.proof(plan, sheet)
    print(f"{len(plan.get('graphics', []))} graphics -> {sheet}")
    print(f"WARNINGS ({len(warnings)}):" if warnings else "no warnings")
    for warning in warnings:
        print("  -", warning)


if __name__ == "__main__":
    main()
