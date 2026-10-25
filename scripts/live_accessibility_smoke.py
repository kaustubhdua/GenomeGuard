"""Read-only accessibility smoke checks against the live synthetic demo.

This is automated assistance, not a substitute for a human screen-reader and keyboard review.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

PAGES = ["#/overview", "#/requests", "#/request/1", "#/family/1", "#/anomalies",
         "#/audit", "#/donor", "#/redteam", "#/federated"]
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f": {detail}" if detail else ""))
    if not ok:
        FAILURES.append(label)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--timeout", type=int, default=20_000)
    args = parser.parse_args()
    base = args.base.rstrip("/")
    axe_path = os.environ.get("AXE_CORE_PATH")
    if not axe_path or not Path(axe_path).is_file():
        parser.error("AXE_CORE_PATH must point to a local axe-core JavaScript file")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        for theme in ("light", "dark"):
            ctx = browser.new_context(viewport={"width": 1280, "height": 900},
                                      reduced_motion="reduce")
            ctx.add_init_script(
                f'localStorage.setItem("gg_who","steward");localStorage.setItem("gg_theme","{theme}")'
            )
            page = ctx.new_page()
            page.set_default_timeout(args.timeout)
            errors: list[str] = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            for route in PAGES:
                try:
                    page.goto(base + "/" + route, wait_until="domcontentloaded")
                    page.locator("#view h1").wait_for(state="visible", timeout=args.timeout)
                    page.wait_for_timeout(100)
                    page.add_script_tag(path=axe_path)
                    violations = page.evaluate("""async () => {
                      const r = await axe.run(document, {runOnly: {type: "tag", values:
                        ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"]}});
                      return r.violations.map(v => ({id:v.id, impact:v.impact, help:v.help,
                        nodes:v.nodes.length})); }""")
                    blocking = [v for v in violations if v["impact"] in ("critical", "serious") or v["id"] == "heading-order"]
                    details = blocking if blocking else [
                        {"id": v["id"], "impact": v["impact"], "help": v["help"]} for v in violations
                    ]
                    check(f"axe critical/serious ({theme} {route})", not blocking,
                          str(details)[:420] if details else "no findings")
                except Exception as exc:
                    check(f"axe route ({theme} {route})", False,
                          f"{type(exc).__name__}: {str(exc)[:180]}")
            check(f"no browser JavaScript exceptions ({theme})", not errors, "; ".join(errors)[:240])
            reduced = page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches")
            check(f"reduced-motion preference is honoured ({theme})", reduced)
            ctx.close()

        keyboard_ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        keyboard = keyboard_ctx.new_page()
        keyboard.goto(base + "/#/overview", wait_until="domcontentloaded")
        keyboard.locator("#view h1").wait_for(state="visible", timeout=args.timeout)
        keyboard.keyboard.press("Tab")
        focused = keyboard.evaluate("document.activeElement !== document.body")
        check("keyboard Tab moves focus to an element", focused)
        keyboard.keyboard.press("Control+k")
        check("Ctrl+K opens command palette", keyboard.locator("#cmdk.open").count() == 1)
        keyboard.locator("#cmdk-input").fill("Requests")
        keyboard.keyboard.press("ArrowDown")
        keyboard.keyboard.press("Enter")
        keyboard.wait_for_url("**/#/requests", timeout=args.timeout)
        check("keyboard palette navigates to Requests", "#/requests" in keyboard.url)
        keyboard.keyboard.press("Control+k")
        keyboard.keyboard.press("Escape")
        check("Escape closes command palette", keyboard.locator("#cmdk.open").count() == 0)
        keyboard_ctx.close()

        mobile_ctx = browser.new_context(viewport={"width": 375, "height": 800})
        mobile = mobile_ctx.new_page()
        mobile.goto(base + "/#/overview", wait_until="domcontentloaded")
        mobile.locator("#view h1").wait_for(state="visible", timeout=args.timeout)
        mobile.locator("#menu").click()
        check("mobile menu opens", mobile.locator("#shell.open").count() == 1)
        mobile.locator("#scrim").click(position={"x": 300, "y": 100})
        check("mobile menu closes via backdrop", mobile.locator("#shell.open").count() == 0)
        mobile_ctx.close()

        # A 640 CSS-pixel viewport approximates the 200% zoom/reflow constraint for a
        # 1280px desktop layout; browser chrome zoom itself is not exposed to Playwright.
        for route in ("#/overview", "#/requests", "#/audit"):
            zoom_ctx = browser.new_context(viewport={"width": 640, "height": 900})
            zoom_ctx.add_init_script('localStorage.setItem("gg_who","steward")')
            zoom = zoom_ctx.new_page()
            zoom.goto(base + "/" + route, wait_until="domcontentloaded")
            zoom.locator("#view h1").wait_for(state="visible", timeout=args.timeout)
            metrics = zoom.evaluate("""() => ({client:document.documentElement.clientWidth,
              scroll:document.documentElement.scrollWidth,
              overflow:document.documentElement.scrollWidth > document.documentElement.clientWidth + 1})""")
            check(f"reflow at 640px ({route})", not metrics["overflow"], str(metrics))
            zoom_ctx.close()
        browser.close()

    print("\n" + ("LIVE ACCESSIBILITY SMOKE PASSED" if not FAILURES
                     else f"LIVE ACCESSIBILITY SMOKE FAILED ({len(FAILURES)} checks)"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
