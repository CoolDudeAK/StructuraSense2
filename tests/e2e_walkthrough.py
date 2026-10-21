"""Browser walkthrough with Playwright: signs in, visits every page, records JS errors, saves screenshots.
Run the server first, then:  python tests/e2e_walkthrough.py http://127.0.0.1:5000"""
import sys, json
from pathlib import Path
from playwright.sync_api import sync_playwright

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000"
out = Path(__file__).parent / "shots"; out.mkdir(exist_ok=True)
errors = []
pages = ["overview", "overview/STR-002", "overview/STR-002?tab=sensors", "overview/STR-002?tab=channels", "overview/STR-001?tab=channels", "elements", "overview/STR-002?tab=trends", "impact/STR-001", "signal", "vision", "alerts", "alerts?tab=tasks", "data", "data?tab=esp32", "data?tab=csv", "sim", "models", "cloud", "business", "register"]
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else None)
    for name, vp in (("desktop", {"width": 1366, "height": 850}), ("mobile", {"width": 390, "height": 800})):
        ctx = b.new_context(viewport=vp); pg = ctx.new_page()
        pg.on("console", lambda m: m.type == "error" and errors.append(f"[{name}] console: {m.text}"))
        pg.on("pageerror", lambda e: errors.append(f"[{name}] pageerror: {e}"))
        pg.on("response", lambda r: r.status >= 400 and "/api/" in r.url and errors.append(f"[{name}] HTTP {r.status} {r.url}"))
        pg.goto(base); pg.wait_for_selector(".auth")
        if name == "desktop": pg.screenshot(path=str(out / "00_login.png"))
        pg.click("text=Engineer — can record"); pg.wait_for_selector(".shell", timeout=15000)
        for i, route in enumerate(pages):
            pg.evaluate(f"location.hash='#/{route}'"); pg.wait_for_timeout(1400)
            txt = pg.inner_text("#main")
            if "Something went wrong" in txt: errors.append(f"[{name}] {route}: page error box")
            if len(txt.strip()) < 40: errors.append(f"[{name}] {route}: nearly empty")
            ow = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            if ow > 2: errors.append(f"[{name}] {route}: horizontal overflow {ow}px")
            pg.screenshot(path=str(out / f"{name}_{i:02d}_{route.replace('/','_').replace('?','_').replace('=','')}.png"), full_page=(name == "desktop"))
        ctx.close()
    b.close()
print("\n".join(errors) if errors else "NO ERRORS")
