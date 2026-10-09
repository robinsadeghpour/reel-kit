#!/usr/bin/env python3
"""Screenshot web pages for use as supporting visuals in a video.

Uses the installed Google Chrome (or the browser `reel setup` downloaded when there is
none), waits in real time so intro animations and games can load, and clicks away cookie
banners where it finds a decline button.

Usage: reel shots OUTDIR name=url [name=url ...] [--wait 10] [--mobile] [--tall 3] [--width 700] [--locale de-DE]

--tall N also saves name-tall.png, the page from the top down to N screens, for scrolling
through inside a video.
"""

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

import kit

# Buttons that turn a cookie notice down. Add your own language's wording here.
DECLINE = ["Decline", "Reject", "Reject all", "Decline all", "Only necessary", "Necessary only", "Ablehnen", "Alle ablehnen", "Alle Cookies ablehnen",
           "Nur notwendige", "Nur essenzielle Cookies", "Refuser", "Tout refuser", "Rechazar", "Rechazar todo", "Rifiuta", "Rifiuta tutto"]


def launch(p):
    flags = ["--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
    try:
        return p.chromium.launch(channel="chrome", headless=True, args=flags)
    except Exception:
        try:
            return p.chromium.launch(headless=True, args=flags)
        except Exception as error:
            raise SystemExit(f"no browser to take screenshots with: install Google Chrome or run `reel setup`\n{str(error).splitlines()[0]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("outdir")
    parser.add_argument("pages", nargs="+")
    parser.add_argument("--wait", type=float, default=10)
    parser.add_argument("--mobile", action="store_true")
    parser.add_argument("--tall", type=float, default=0)
    parser.add_argument("--width", type=int, default=1280, help="window width; narrower makes a page's text larger in the capture")
    parser.add_argument("--locale", help="language the pages are asked for, e.g. de-DE; default is \"locale\" in reel.json, else en-US")
    args = parser.parse_args()
    kit.find_project()
    locale = args.locale or kit.settings().get("locale", "en-US")
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    viewport = {"width": 430, "height": 860} if args.mobile else {"width": args.width, "height": round(args.width * 0.625)}
    with sync_playwright() as p:
        browser = launch(p)
        context = browser.new_context(viewport=viewport, device_scale_factor=3 if args.mobile else 2, is_mobile=args.mobile, has_touch=args.mobile, locale=locale)
        for item in args.pages:
            name, url = item.split("=", 1)
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(args.wait * 1000)
                # Cookie notices often sit in their own frame, so look in every frame.
                declined = False
                for frame in page.frames:
                    for label in DECLINE:
                        try:
                            button = frame.get_by_role("button", name=label, exact=True)
                            if not button.count():
                                button = frame.get_by_text(label, exact=True)  # some notices use plain links or custom elements
                            if button.count():
                                button.first.click(timeout=2000)
                                page.wait_for_timeout(900)
                                declined = True
                                break
                        except Exception:
                            continue
                    if declined:
                        break
                target = out / f"{name}{'-mobile' if args.mobile else ''}.png"
                page.screenshot(path=str(target))
                print(target, page.title())
                if args.tall:
                    # Scroll through once so lazy sections load, then capture from the top.
                    height = page.evaluate("document.documentElement.scrollHeight")
                    wanted = min(height, int(viewport["height"] * args.tall))
                    for y in range(0, wanted, viewport["height"] // 2):
                        page.evaluate(f"window.scrollTo(0, {y})")
                        page.wait_for_timeout(350)
                    page.evaluate("window.scrollTo(0, 0)")
                    page.wait_for_timeout(700)
                    tall = out / f"{name}-tall.png"
                    page.screenshot(path=str(tall), full_page=True, clip={"x": 0, "y": 0, "width": viewport["width"], "height": wanted})
                    print(tall, f"{wanted}px of {height}px")
            except Exception as error:
                print(name, "failed:", str(error).splitlines()[0])
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
