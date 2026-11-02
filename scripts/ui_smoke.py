"""`make ui-smoke`: drives the real UI in a headless browser and fails on regressions.

    pip install playwright && playwright install chromium     # one-time, on your machine
    python scripts/ui_smoke.py --base http://127.0.0.1:8000   # server in demo mode, FRESH database

Checks, on every page, in light and dark themes:
  * no JavaScript errors (the one expected network "403" from the frozen probe account is ignored)
  * no horizontal page scroll at 320, 375 and 414 px wide
  * every visible text element has WCAG AA contrast (4.5:1; 3:1 for large text)
  * every button and link has a name, every input has a label, each page has one h1
  * buttons and form controls are at least 24 px tall and wide
It exercises steward VCF upload, malformed and oversized inputs, gzip input, and JSON/text exports.
It also plays the guided tour end to end, including its two live actions, and checks the results.
The run changes server state (it sends requests and freezes the probe account), so use a fresh DB.
Set CHROMIUM_PATH to use a browser that is already installed.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

PAGES = ["#/overview", "#/requests", "#/request/1", "#/family/1", "#/anomalies", "#/audit",
         "#/datasets", "#/chromosomes", "#/variants", "#/sources", "#/dataset-qc",
         "#/donor", "#/redteam", "#/federated"]

QC_VCF_HEADER = """##fileformat=VCFv4.2
##reference=GRCh38
##contig=<ID=1,length=248956422>
##INFO=<ID=DP,Number=1,Type=Integer,Description="Read depth">
##FILTER=<ID=PASS,Description="All filters passed">
##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE_A\tSAMPLE_B
"""

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


def check_vcf_qc_workflow(browser, base: str) -> None:
    print("\n3. Steward VCF QC upload and report exports")
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(base + "/#/overview")
    page.wait_for_selector("#who option[value='steward']", timeout=30000)
    menu_button = page.locator("#menu")
    if menu_button.is_visible():
        menu_button.click()
    page.locator("#who").select_option("steward")
    page.goto(base + "/#/dataset-qc")
    page.wait_for_selector(".qc-upload", timeout=15000)

    with tempfile.TemporaryDirectory(prefix="genomeguard-ui-vcf-qc-") as directory:
        temporary = Path(directory)
        valid_vcf = temporary / "synthetic-fixture.vcf"
        valid_vcf.write_text(
            QC_VCF_HEADER + "1\t100\t.\tA\tG\t50\tPASS\t.\tGT\t0/1\t0/0\n",
            encoding="utf-8",
        )
        file_input = page.get_by_label("Select VCF or gzip-compressed VCF")
        page.get_by_label("Reference assembly").select_option("GRCh38")
        file_input.set_input_files(str(valid_vcf))
        page.wait_for_function(
            "() => !document.querySelector('.qc-upload button[type=\"submit\"]')?.disabled",
            timeout=10000,
        )
        page.get_by_role("button", name="Run VCF QC").click()
        page.wait_for_selector(".qc-report", timeout=60000)
        report_status = page.locator(".qc-report-head h2").inner_text()
        eligibility = page.locator(".qc-report").inner_text()
        check("valid VCF upload completes with warnings, not false approval",
              "passed with warnings" in report_status.lower()
              and "NOT ESTABLISHED" in eligibility, report_status)

        with page.expect_download() as json_download_info:
            page.get_by_role("button", name="Download JSON").click()
        json_download = json_download_info.value
        json_path = temporary / json_download.suggested_filename
        json_download.save_as(str(json_path))
        exported = json.loads(json_path.read_text(encoding="utf-8"))
        serialized = json.dumps(exported)
        check("JSON report includes measured metrics and redacts sample identifiers",
              exported.get("statistics", {}).get("split_variant_count") == 1
              and exported.get("statistics", {}).get("genotype_cells") == 2
              and exported.get("import_eligibility") == "NOT_ESTABLISHED"
              and exported.get("file", {}).get("name") == "[redacted from export]"
              and "SAMPLE_A" not in serialized and "SAMPLE_B" not in serialized)

        with page.expect_download() as text_download_info:
            page.get_by_role("button", name="Download human-readable report").click()
        text_download = text_download_info.value
        text_path = temporary / text_download.suggested_filename
        text_download.save_as(str(text_path))
        text_report = text_path.read_text(encoding="utf-8")
        check("human-readable report preserves QC status and import boundary",
              "Validation: PASSED_WITH_WARNINGS" in text_report
              and "Import eligibility: NOT_ESTABLISHED" in text_report
              and "SAMPLE_A" not in text_report and "SAMPLE_B" not in text_report)

        invalid_vcf = temporary / "malformed.vcf"
        invalid_vcf.write_text(
            QC_VCF_HEADER + "1\tinvalid\t.\tA\tG\t50\tPASS\t.\tGT\t0/1\t0/0\n",
            encoding="utf-8",
        )
        file_input.set_input_files(str(invalid_vcf))
        page.wait_for_function(
            "() => !document.querySelector('.qc-upload button[type=\"submit\"]')?.disabled",
            timeout=10000,
        )
        page.get_by_role("button", name="Run VCF QC").click()
        page.wait_for_function(
            "() => document.querySelector('.qc-report-head h2')?.textContent.includes('failed')",
            timeout=60000,
        )
        check("malformed VCF is reported as failed validation",
              "failed" in page.locator(".qc-report-head h2").inner_text().lower())

        compressed_vcf = temporary / "synthetic-fixture.vcf.gz"
        with gzip.open(compressed_vcf, "wt", encoding="utf-8") as stream:
            stream.write(QC_VCF_HEADER + "1\t101\t.\tC\tT\t.\tPASS\t.\tGT\t0/1\t./.\n")
        file_input.set_input_files(str(compressed_vcf))
        page.wait_for_function(
            "() => !document.querySelector('.qc-upload button[type=\"submit\"]')?.disabled",
            timeout=10000,
        )
        page.get_by_role("button", name="Run VCF QC").click()
        page.wait_for_selector(".qc-report", timeout=60000)
        check("gzip-compressed VCF upload completes",
              "passed with warnings" in page.locator(".qc-report-head h2").inner_text().lower())

        oversized_vcf = temporary / "oversized.vcf"
        with oversized_vcf.open("wb") as stream:
            stream.write(QC_VCF_HEADER.encode("utf-8"))
            stream.truncate(100 * 1024 * 1024 + 1)
        file_input.set_input_files(str(oversized_vcf))
        page.wait_for_function(
            "() => document.querySelector('.qc-upload > [role=\"status\"]')?.textContent.includes('exceeds the 100 MiB upload limit')",
            timeout=10000,
        )
        upload_disabled = page.get_by_role("button", name="Run VCF QC").is_disabled()
        check("oversized VCF is rejected before upload",
              upload_disabled and "exceeds the 100 MiB upload limit"
              in page.locator('.qc-upload > [role="status"]').inner_text())

    check("no JavaScript errors during VCF QC workflow", not errors, "; ".join(errors)[:160])
    context.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    base = ap.parse_args().base.rstrip("/")
    launch = {"args": ["--no-sandbox"]}
    if os.environ.get("CHROMIUM_PATH"):
        launch["executable_path"] = os.environ["CHROMIUM_PATH"]

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch)
        screenshot_dir = os.environ.get("UI_SCREENSHOT_DIR")
        if screenshot_dir:
            Path(screenshot_dir).mkdir(parents=True, exist_ok=True)

        print("\\n0. Keyboard navigation and command palette")
        keyboard_ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        # Real-data mode intentionally does not restore identities from browser storage.
        # Exercise a public route so this smoke test never relies on a fabricated steward.
        keyboard_pg = keyboard_ctx.new_page()
        keyboard_pg.goto(base + "/#/overview")
        keyboard_pg.wait_for_selector("#view h1", timeout=15000)
        keyboard_pg.keyboard.press("Control+k")
        palette_open = keyboard_pg.locator("#cmdk.open").count() == 1
        keyboard_pg.locator("#cmdk-input").fill("Datasets")
        keyboard_pg.keyboard.press("ArrowDown")
        keyboard_pg.keyboard.press("Enter")
        keyboard_pg.wait_for_url("**/#/datasets", timeout=15000)
        keyboard_pg.keyboard.press("Control+k")
        keyboard_pg.keyboard.press("Escape")
        palette_closes = keyboard_pg.locator("#cmdk.open").count() == 0
        check("Ctrl+K opens command palette", palette_open)
        check("keyboard search can navigate to Dataset catalogue", "#/datasets" in keyboard_pg.url)
        check("Escape closes command palette", palette_closes)
        keyboard_ctx.close()

        print("\\n0. Startup resilience when browser storage is blocked")
        blocked_ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        blocked_ctx.add_init_script(
            "Object.defineProperty(window, 'localStorage', {"
            "get() { throw new DOMException('Blocked', 'SecurityError'); }"
            "});"
        )
        blocked_pg = blocked_ctx.new_page()
        blocked_pg.goto(base + "/#/overview")
        blocked_pg.wait_for_selector("#view h1", timeout=15000)
        check("overview renders when localStorage is unavailable",
              blocked_pg.locator("#view h1").count() == 1)
        blocked_ctx.close()

        print("\\n0. Route-level lazy loading and page entrance motion")
        lazy_ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        lazy_pg = lazy_ctx.new_page()
        lazy_pg.goto(base + "/#/overview")
        lazy_pg.wait_for_selector("#view h1", timeout=15000)
        loaded_before = lazy_pg.evaluate("performance.getEntriesByType('resource').map(e => e.name)")
        requests_loaded_early = any(name.endswith("/pages/requests.js") for name in loaded_before)
        lazy_pg.goto(base + "/#/requests")
        lazy_pg.wait_for_selector("#view h1", timeout=15000)
        loaded_after = lazy_pg.evaluate("performance.getEntriesByType('resource').map(e => e.name)")
        requests_loaded_on_visit = any(name.endswith("/pages/requests.js") for name in loaded_after)
        has_enter_class = lazy_pg.locator("#view > .page-enter").count() == 1
        check("non-current route module is not loaded at startup", not requests_loaded_early)
        check("route module loads when visited", requests_loaded_on_visit)
        check("route transition uses entrance class", has_enter_class)
        lazy_ctx.close()

        motion_ctx = browser.new_context(viewport={"width": 1280, "height": 900}, reduced_motion="reduce")
        motion_pg = motion_ctx.new_page()
        motion_pg.goto(base + "/#/overview")
        motion_pg.wait_for_selector("#view > .page-enter", timeout=15000)
        duration = motion_pg.locator("#view > .page-enter").evaluate("(e) => getComputedStyle(e).animationDuration")
        check("reduced-motion preference disables page animation", float(duration.removesuffix("s")) <= 0.001, duration)
        motion_ctx.close()

        print("\n0. Product navigation and demo-only research lab")
        nav_ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        nav_ctx.add_init_script("localStorage.setItem('gg_who','steward')")
        nav_pg = nav_ctx.new_page()
        nav_pg.goto(base + "/#/overview")
        nav_pg.wait_for_selector("#who option[value='steward']", timeout=30000)
        nav_pg.wait_for_function(
            "() => document.querySelectorAll('#nav .nav-label').length >= 5",
            timeout=15000,
        )
        steward_sections = nav_pg.locator("#nav .nav-label").all_text_contents()
        check("steward navigation groups core workflows and separates the research lab",
              steward_sections == ["Overview", "Dataset Explorer", "Steward Review",
                                   "Audit & Security", "Research Lab"],
              ", ".join(steward_sections))
        review_links = nav_pg.locator(
            "#nav .nav-group", has=nav_pg.locator(".nav-label", has_text="Steward Review")
        ).locator("a").all_text_contents()
        check("steward request queue stays under Steward Review",
              any("Request review queue" in text for text in review_links))
        researcher_keys = nav_pg.locator("#who option:not([value='steward'])").evaluate_all(
            "(options) => options.map((option) => option.value).filter(Boolean)"
        )
        if researcher_keys:
            nav_pg.locator("#who").select_option(researcher_keys[0])
            nav_pg.wait_for_function(
                "() => [...document.querySelectorAll('#nav .nav-label')].some("
                "(label) => label.textContent === 'Research Requests')",
                timeout=15000,
            )
            researcher_sections = nav_pg.locator("#nav .nav-label").all_text_contents()
            check("researcher navigation hides steward tools and keeps the lab separate",
                  researcher_sections == ["Overview", "Dataset Explorer",
                                          "Research Requests", "Research Lab"],
                  ", ".join(researcher_sections))
        else:
            check("researcher navigation can be checked", False,
                  "demo server did not provide a researcher persona")
        nav_ctx.close()

        print("\n1. The guided tour, with its two live actions (fresh database expected)")
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        pg = ctx.new_page()
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        # Fail-closed readiness intentionally returns HTTP 503 until production
        # prerequisites are met. Track HTTP failures by URL rather than treating
        # Chromium's generic resource-load console message as a JavaScript exception.
        def check_response(response):
            if response.status >= 500:
                path = response.url.split("?", 1)[0].rstrip("/")
                if path.endswith("/health/ready"):
                    return
                errors.append(f"HTTP {response.status}: {path}")
        pg.on("response", check_response)
        pg.goto(base + "/#/overview", wait_until="domcontentloaded")
        # Demo identity is hydrated asynchronously by boot(); wait for the real control
        # instead of assuming the API and dataset bootstrap finish within 1.5 seconds.
        tour_button = pg.get_by_role("button", name="Guided walkthrough")
        tour_button.wait_for(state="visible", timeout=30000)
        tour_button.click()
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
                pg.wait_for_timeout(150)
                # Wait for finite route/timeline entrance animations before measuring contrast;
                # otherwise axe can report a transient low-opacity frame as a contrast failure.
                pg.evaluate("""async () => {
                  const finite = document.getAnimations({subtree: true}).filter((animation) => {
                    const timing = animation.effect?.getComputedTiming();
                    return timing && Number.isFinite(timing.endTime);
                  });
                  await Promise.all(finite.map((animation) => animation.finished.catch(() => {})));
                }""")
                axe_path = os.environ.get("AXE_CORE_PATH")
                if axe_path:
                    pg.add_script_tag(path=axe_path)
                    axe_violations = pg.evaluate("""async () => {
                      const result = await axe.run(document, {runOnly: {type: "tag", values: [
                        "wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"
                      ]}});
                      return result.violations.map(v => ({id:v.id, impact:v.impact, help:v.help,
                        targets:v.nodes.slice(0, 4).map(n => n.target)}));
                    }""")
                    blocking = [v for v in axe_violations if v["impact"] in ("critical", "serious")]
                    check(f"{hsh} axe critical/serious", not blocking,
                          str(blocking)[:260] if blocking else f"{len(axe_violations)} non-blocking finding(s)")
                r = pg.evaluate(AUDIT_JS)
                if hsh == "#/sources":
                    lifecycle_count = pg.locator("article.source-card details.source-lifecycle").count()
                    first_lifecycle = pg.locator(
                        "article.source-card details.source-lifecycle summary"
                    ).first
                    first_lifecycle.click()
                    lifecycle_text = pg.locator(
                        "article.source-card details.source-lifecycle"
                    ).first.inner_text()
                    check(f"{hsh} distinguishes source lifecycle stages",
                          lifecycle_count == 3 and "Downloaded" in lifecycle_text
                          and "Not started" in lifecycle_text
                          and "Pending exact-artifact review" in lifecycle_text
                          and "Not imported" in lifecycle_text)
                if hsh == "#/requests":
                    history_layout = pg.evaluate("""() => {
                      const card = document.querySelector(".request-history");
                      const table = card?.querySelector("table");
                      const date = table?.querySelector("tbody tr td:nth-child(2)");
                      if (!card || !table || !date) return {missing: true};
                      const cardRect = card.getBoundingClientRect();
                      const tableRect = table.getBoundingClientRect();
                      return {missing: false, cardWidth: cardRect.width, tableWidth: tableRect.width,
                        tableUsesCard: tableRect.width >= cardRect.width * 0.8,
                        timestampWhiteSpace: getComputedStyle(date).whiteSpace};
                    }""")
                    check("request history uses full card width and readable timestamps",
                          not history_layout.get("missing") and history_layout.get("tableUsesCard")
                          and history_layout.get("timestampWhiteSpace") == "nowrap", str(history_layout))
                if hsh == "#/overview":
                    proof_layout = pg.evaluate("""() => {
                      const panel = document.querySelector(".gg-evidence");
                      const grid = panel?.querySelector(".gg-evidence-grid");
                      if (!panel || !grid) return {missing: true};
                      const panelRect = panel.getBoundingClientRect();
                      const values = [...grid.querySelectorAll(".gg-fact strong")];
                      const cols = getComputedStyle(grid).gridTemplateColumns.split(" ").map(parseFloat);
                      return {missing: false, panelWidth: panelRect.width, columnCount: cols.length,
                        valueCount: values.length,
                        valuesFit: values.length === 3 && values.every(e => e.scrollWidth <= e.clientWidth + 1 &&
                          e.getBoundingClientRect().right <= panelRect.right - 8 && e.clientWidth >= 100)};
                    }""")
                    check("overview evidence metrics render without clipping",
                          not proof_layout.get("missing") and proof_layout.get("columnCount") == 3
                          and proof_layout.get("valuesFit", False), str(proof_layout))
                bad = {k: v for k, v in r.items() if isinstance(v, list) and v}
                check(f"{hsh}", r["h1"] == 1 and not bad,
                      str(bad)[:140] if bad else ("h1 count " + str(r["h1"]) if r["h1"] != 1 else ""))
                if screenshot_dir:
                    shot_name = theme + "-" + hsh.strip("#/").replace("/", "-") + ".png"
                    pg.screenshot(path=str(Path(screenshot_dir) / shot_name), full_page=True,
                                  animations="disabled")
            check(f"no JavaScript errors ({theme})", not errs, "; ".join(errs)[:120])

        check_vcf_qc_workflow(browser, base)

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
            if screenshot_dir and width == 375:
                ctx = browser.new_context(viewport={"width": width, "height": 812})
                shot = ctx.new_page()
                shot.goto(base + "/#/overview")
                shot.wait_for_selector("#view h1", timeout=15000)
                shot.screenshot(path=str(Path(screenshot_dir) / "mobile-375-overview.png"),
                                full_page=True, animations="disabled")
                ctx.close()
        browser.close()

    print("\n" + ("ALL UI CHECKS PASSED" if not failures else f"{len(failures)} UI CHECK(S) FAILED"))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
