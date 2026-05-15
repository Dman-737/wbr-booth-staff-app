"""
WBR Booth Staff Report scraper.

Logs into the ExpoGenie WBR portal, pulls the Booth Staff Report and User Report,
joins them on Exhibiting Company, and writes a JSON file the frontend can read.

Run locally:
    EG_USERNAME=... EG_PASSWORD=... python scraper.py

Run in GitHub Actions:
    Env vars set via repository secrets.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

# Hardcoded for the WBR side project. Add more events here later if needed.
EVENTS = [
    {
        "slug": "etailboston26",
        "name": "eTail Boston 2026",
        "base_url": "https://wbr.expo-genie.com/etailboston26",
    },
]

USERNAME = os.environ.get("EG_USERNAME")
PASSWORD = os.environ.get("EG_PASSWORD")

if not USERNAME or not PASSWORD:
    print("ERROR: EG_USERNAME and EG_PASSWORD env vars are required.", file=sys.stderr)
    sys.exit(1)


def refined_summit_rule(level: str) -> str:
    """Take the prefix before the first underscore; keep it only if it ends with 'Summit'."""
    if not level:
        return ""
    prefix = level.split("_")[0].strip()
    return prefix if prefix.lower().endswith("summit") else ""


def login(page, base_url: str) -> None:
    """Log into the WordPress admin for this event portal."""
    page.goto(f"{base_url}/wp-login.php", wait_until="domcontentloaded")
    page.fill("#user_login", USERNAME)
    page.fill("#user_pass", PASSWORD)
    page.click("#wp-submit")
    page.wait_for_load_state("networkidle", timeout=30_000)
    # WordPress periodically interrupts admin login with a "confirm admin email" prompt.
    # If we hit it, dismiss it by following the "remind me later" action.
    if "action=confirm_admin_email" in page.url:
        page.goto(f"{base_url}/wp-login.php?action=admin_email_remind_later", wait_until="networkidle")
    # Verify login by checking for the WordPress auth cookie (URL pattern is unreliable).
    cookies = page.context.cookies()
    auth_cookie = next((c for c in cookies if c["name"].startswith("wordpress_logged_in")), None)
    if not auth_cookie:
        raise Exception(f"Login failed - no auth cookie. URL: {page.url}")


def scrape_user_report(page, base_url: str) -> dict:
    """Return {company_name_lowercase: level_string} from the User Report."""
    page.goto(f"{base_url}/user-report-result/?report=All+Users", wait_until="domcontentloaded", timeout=60_000)
    # Wait for the DataTable to render
    page.wait_for_selector("table tbody tr td", timeout=45_000)
    rows = page.evaluate("""() => {
        const t = document.querySelectorAll('table')[0];
        if (!t) return [];
        const headers = [...t.querySelectorAll('thead th')].map(th => th.innerText.trim());
        const compIdx = headers.indexOf('Company Name');
        const lvlIdx = headers.indexOf('Level');
        return [...t.querySelectorAll('tbody tr')].map(tr => {
            const cells = [...tr.querySelectorAll('td')].map(td => td.innerText.trim());
            return [cells[compIdx] || '', cells[lvlIdx] || ''];
        });
    }""")
    level_map = {}
    for company, level in rows:
        if not company or not level:
            continue
        # 'Content Manager' is the internal WBR admin role — skip it
        if level.strip().lower() == "content manager":
            continue
        level_map[company.lower().strip()] = level
    return level_map


def scrape_booth_staff(page, base_url: str) -> list:
    """Return list of booth staff dicts from the Booth Staff Report."""
    page.goto(f"{base_url}/booth-staff-report/", wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_selector("table tbody tr td", timeout=45_000)
    rows = page.evaluate("""() => {
        // The booth staff table is index 1 (index 0 is sometimes a filter helper)
        const tables = document.querySelectorAll('table');
        let t = null;
        for (const candidate of tables) {
            const headers = [...candidate.querySelectorAll('thead th')].map(th => th.innerText.trim());
            if (headers.includes('Exhibiting Company')) { t = candidate; break; }
        }
        if (!t) return [];
        const headers = [...t.querySelectorAll('thead th')].map(th => th.innerText.trim());
        const wanted = ['Exhibiting Company','First Name','Last Name','Email','Company Name','Registration Date','Pass Type','Job Title','Company Mailing Address','Mobile Number','Reg Code','Created Date'];
        const idx = {};
        wanted.forEach(w => { idx[w] = headers.indexOf(w); });
        return [...t.querySelectorAll('tbody tr')].map(tr => {
            const cells = [...tr.querySelectorAll('td')].map(td => td.innerText.trim());
            const obj = {};
            wanted.forEach(w => { obj[w] = idx[w] >= 0 ? (cells[idx[w]] || '') : ''; });
            return obj;
        });
    }""")
    return rows


def scrape_event(event: dict) -> dict:
    """Scrape a single event portal and return the joined data."""
    base_url = event["base_url"]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        try:
            login(page, base_url)
            level_map = scrape_user_report(page, base_url)
            booth_staff = scrape_booth_staff(page, base_url)
        finally:
            context.close()
            browser.close()

    # Join and apply the parsing rule
    joined = []
    for r in booth_staff:
        exh = r.get("Exhibiting Company", "")
        level = level_map.get(exh.lower().strip(), "")
        joined.append({
            "exhibiting": exh,
            "firstName": r.get("First Name", ""),
            "lastName": r.get("Last Name", ""),
            "email": r.get("Email", ""),
            "company": r.get("Company Name", ""),
            "title": r.get("Job Title", ""),
            "regType": r.get("Pass Type", ""),
            "regDate": r.get("Registration Date", ""),
            "regCode": r.get("Reg Code", ""),
            "phone": r.get("Mobile Number", ""),
            "address": r.get("Company Mailing Address", ""),
            "level": level,
            "summit": refined_summit_rule(level),
        })

    return {
        "event": {
            "slug": event["slug"],
            "name": event["name"],
            "portalUrl": base_url,
        },
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total": len(joined),
            "matched": sum(1 for r in joined if r["level"]),
            "unmatched": sum(1 for r in joined if not r["level"]),
            "withSummit": sum(1 for r in joined if r["summit"]),
            "exhibitors": len({r["exhibiting"] for r in joined if r["exhibiting"]}),
        },
        "rows": joined,
    }


def main():
    out_dir = Path(__file__).parent / "data"
    out_dir.mkdir(exist_ok=True)

    all_events = []
    for event in EVENTS:
        print(f"Scraping {event['slug']}...", flush=True)
        try:
            result = scrape_event(event)
            print(f"  {result['stats']['total']} staff, {result['stats']['matched']} matched, {result['stats']['withSummit']} with Summit", flush=True)
            # Write per-event JSON
            (out_dir / f"{event['slug']}.json").write_text(json.dumps(result, indent=2))
            all_events.append(result)
        except Exception as e:
            print(f"  FAILED: {e}", file=sys.stderr, flush=True)
            sys.exit(1)

    # Convenience: also write a 'latest.json' pointing at the most recent successful scrape
    if all_events:
        (out_dir / "latest.json").write_text(json.dumps(all_events[0], indent=2))

    print("Done.", flush=True)


if __name__ == "__main__":
    main()
