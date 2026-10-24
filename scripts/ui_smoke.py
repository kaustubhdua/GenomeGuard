"""`make ui-smoke`: drives the real UI in a headless browser and fails on regressions.

    pip install playwright && playwright install chromium     # one-time, on your machine
    python scripts/ui_smoke.py --base http://127.0.0.1:8000   # server in demo mode, FRESH database

Checks, on every page, in light and dark themes:
  * no JavaScript errors (the one expected network "403" from the frozen probe account is ignored)
  * no horizontal page scroll at 320, 375 and 414 px wide
  * every visible text element has WCAG AA contrast (4.5:1; 3:1 for large text)
  * every button and link has a name, every input has a label, each page has one h1
  * buttons and form controls are at least 24 px tall and wide
And it plays the guided tour end to end, including its two live actions, and checks the results.
The run changes server state (it sends requests and freezes the probe account), so use a fresh DB.
Set CHROMIUM_PATH to use a browser that is already installed.
"""

from __future__ import annotations

import argparse
import os
import sys

from playwright.sync_api import sync_playwright

PAGES = ["#/overview", "#/requests", "#/request/1", "#/family/1", "#/anomalies", "#/audit",
         "#/donor", "#/redteam", "#/federated"]

AUDIT_JS = r"""
() => {
  const out = {noname: [], nolabel: [], contrast: [], small: [], h1: document.querySelectorAll('h1').length};
  const parse = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(',').map(parseFloat); return {r:p[0], g:p[1], b:p[2], a: p.length > 3 ? p[3] : 1}; };
  const lum = ({r,g,b}) => { const f = v => { v/=255; return v<=0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4) }; return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b); };
  const bgOf = (el) => { const layers = []; for (let e = el; e; e = e.parentElement) { const c = parse(getComputedStyle(e).backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
    let cur = {r:255,g:255,b:255}; if (!layers.length || layers[layers.length-1].a < 1) { const bc = parse(getComputedStyle(document.body).backgroundColor); if (bc && bc.a>0) cur = bc; }
    for (let i = layers.length-1; i >= 0; i--) { const l = layers[i]; cur = {r: l.r*l.a+cur.r*(1-l.a), g: l.g*l.a+cur.g*(1-l.a), b: l.b*l.a+cur.b*(1-l.a)}; } return cur; };
  const visible = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity) > 0.05; };
  const name = (e) => (e.getAttribute('aria-label') || e.getAttribute('title') || e.textContent || '').trim();
  for (const e of document.querySelectorAll('button, a[href], [role=button]')) if (visible(e) && !name(e)) out.noname.push(e.outerHTML.slice(0, 80));
  for (const e of document.querySelectorAll('input, select, textarea')) { if (!visible(e) || e.type === 'hidden') continue;
    if (!(e.getAttribute('aria-label') || e.getAttribute('aria-labelledby') || (e.id && document.querySelector('label[for="'+e.id+'"]')) || e.closest('label'))) out.nolabel.push(e.outerHTML.slice(0, 80)); }
  const seen = new Set(); const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (w.nextNode()) { const t = w.currentNode; if (!t.textContent.trim()) continue; const e = t.parentElement;
    if (!e || seen.has(e) || !visible(e) || e.closest('svg') || e.closest('[disabled]') || e.closest('[aria-hidden=true]')) continue; seen.add(e);
    const s = getComputedStyle(e); const fg = parse(s.color); if (!fg) continue; const bg = bgOf(e);
    const f2 = {r: fg.r*fg.a+bg.r*(1-fg.a), g: fg.g*fg.a+bg.g*(1-fg.a), b: fg.b*fg.a+bg.b*(1-fg.a)};
    const a = lum(f2), b = lum(bg); const ratio = (Math.max(a,b)+0.05)/(Math.min(a,b)+0.05);
    const px = parseFloat(s.fontSize), large = px >= 24 || (px >= 18.66 && parseInt(s.fontWeight) >= 700);
    if (ratio < (large ? 3 : 4.5)) out.contrast.push(ratio.toFixed(2) + ' ' + e.tagName + '.' + (e.className||'').toString().slice(0,20) + ' "' + t.textContent.trim().slice(0,24) + '"'); }
  for (const e of document.querySelectorAll('button, [role=button], select, input:not([type=checkbox]):not([type=radio]), nav a')) { if (!visible(e)) continue; const r = e.getBoundingClientRect(); if (r.height < 24 || r.width < 24) out.small.push(e.tagName + ' ' + Math.round(r.width) + 'x' + Math.round(r.height) + ' ' + name(e).slice(0,20)); }
  return out;
}
"""

OVERFLOW_JS = """() => {
  const vw = document.documentElement.clientWidth;
  const offenders = [...document.querySelectorAll('body *')].filter((e) => {
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.right > vw + 1 && getComputedStyle(e).position !== 'fixed';
  }).slice(0, 12).map((e) => {
    const r = e.getBoundingClientRect();
    const s = getComputedStyle(e);
    return {tag:e.tagName.toLowerCase(), id:e.id, cls:typeof e.className === 'string' ? e.className.slice(0,70) : '',
      left:Math.round(r.left), right:Math.round(r.right), width:Math.round(r.width),
      scrollWidth:e.scrollWidth, clientWidth:e.clientWidth, position:s.position, text:(e.textContent||'').trim().slice(0,50)};
  });
  return {overflow:document.documentElement.scrollWidth > vw + 1,
    viewport:vw, documentWidth:document.documentElement.scrollWidth, offenders:offenders.slice(0,12)};
}"""
failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(label)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    base = ap.parse_args().base.rstrip("/")
    launch = {"args": ["--no-sandbox"]}
    if os.environ.get("CHROMIUM_PATH"):
        launch["executable_path"] = os.environ["CHROMIUM_PATH"]

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch)

        print("\n1. The guided tour, with its two live actions (fresh database expected)")
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        pg = ctx.new_page()
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error"
              and "403" not in m.text else None)
        pg.goto(base + "/#/overview")
        pg.wait_for_timeout(1500)
        pg.get_by_role("button", name="Take the 3-minute tour").click()
        notes: dict[int, str] = {}
        for step in range(1, 9):
            if step in (2, 4):
                pg.locator(".tour-btns button", has_text="Send the researcher's request"
                           if step == 2 else "Run the probing account").click()
                pg.wait_for_selector(".tour-note:not([hidden])", timeout=60000)
                notes[step] = pg.locator(".tour-note").inner_text()
            pg.wait_for_timeout(900)
            if step < 8:
                pg.locator(".tour-btns button", has_text="Next").click()
        pg.locator(".tour-btns button", has_text="Finish").click()
        check("researcher request approved with protections",
              "Approved with protections" in notes.get(2, ""), notes.get(2, "")[:60])
        check("probe account frozen by the monitor", "frozen" in notes.get(4, ""),
              notes.get(4, "")[:60])
        check("tour closes", pg.locator(".tour").count() == 0)
        check("no JavaScript errors during the tour", not errors, "; ".join(errors)[:120])

        for theme in ("light", "dark"):
            print(f"\n2. Every page, {theme} theme: contrast, names, labels, targets")
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            ctx.add_init_script("localStorage.setItem('gg_who','steward');"
                                f"localStorage.setItem('gg_theme','{theme}')")
            pg = ctx.new_page()
            errs: list[str] = []
            pg.on("pageerror", lambda e, errs=errs: errs.append(str(e)))
            for hsh in PAGES:
                pg.goto(base + "/" + hsh)
                try:  # pages render after their API calls; wait for the heading, not a fixed time
                    pg.wait_for_selector("#view h1", timeout=15000)
                except Exception:
                    pass  # the audit below reports "h1 count 0" if it truly never appears
                pg.wait_for_timeout(600)
                r = pg.evaluate(AUDIT_JS)
                bad = {k: v for k, v in r.items() if isinstance(v, list) and v}
                check(f"{hsh}", r["h1"] == 1 and not bad,
                      str(bad)[:140] if bad else ("h1 count " + str(r["h1"]) if r["h1"] != 1 else ""))
            check(f"no JavaScript errors ({theme})", not errs, "; ".join(errs)[:120])

        print("\n3. No horizontal scroll on phones")
        for width in (320, 375, 414):
            ctx = browser.new_context(viewport={"width": width, "height": 800})
            ctx.add_init_script("localStorage.setItem('gg_who','steward')")
            pg = ctx.new_page()
            over = []
            for hsh in PAGES:
                pg.goto(base + "/" + hsh)
                pg.wait_for_timeout(1200)
                layout = pg.evaluate(OVERFLOW_JS)
                if layout["overflow"]:
                    over.append(f"{hsh}: {layout['viewport']}px viewport / {layout['documentWidth']}px document; "
                                + str(layout["offenders"][:5]))
            check(f"{width}px wide", not over, "; ".join(over)[:900])
        browser.close()

    print("\n" + ("ALL UI CHECKS PASSED" if not failures else f"{len(failures)} UI CHECK(S) FAILED"))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
