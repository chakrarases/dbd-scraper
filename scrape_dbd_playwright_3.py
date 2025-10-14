import argparse
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

SEARCH_URL = "https://datawarehouse.dbd.go.th/searchJuristic"
OUTPUT_DIR = "data"


def is_valid_juristic_id(value: str) -> bool:
    return bool(re.fullmatch(r"\d{13}", value))


def first_visible(page: Page, selectors: List[str], timeout_ms: int = 0):
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if timeout_ms:
                loc.first.wait_for(state="visible", timeout=timeout_ms)
            if loc.first.is_visible():
                return loc.first
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue
    return None


def try_click(page: Page, locators: List[Any], timeout_ms: int = 2000) -> bool:
    for loc in locators:
        try:
            if isinstance(loc, str):
                locator = page.locator(loc)
            else:
                locator = loc
            locator.first.wait_for(state="visible", timeout=timeout_ms)
            locator.first.click(timeout=timeout_ms)
            return True
        except Exception:
            continue
    return False


def accept_cookies(page: Page):
    # Common consent patterns (Thai + English)
    names = [
        "ยอมรับ",
        "ยินยอม",
        "ตกลง",
        "รับทราบ",
        "Accept",
        "Agree",
        "I agree",
        "Accept all",
    ]
    btns = [page.get_by_role("button", name=name) for name in names]
    try_click(page, btns, timeout_ms=1500)


def fill_search_and_submit(page: Page, juristic_id: str, verbose: bool = False):
    # Attempt multiple selector strategies for the search input
    input_selectors = [
        '#key-word',
        'input[name="textSearch"]',
        'form#form input.form-control',
        'input[name="search"]',
        'input[id*="search"]',
        'input[placeholder*="ค้นหา"]',
        'input[placeholder*="นิติบุคคล"]',
        'input[placeholder*="เลข"]',
        'input[placeholder*="Juristic" i]',
        'input[placeholder*="Registration" i]',
        'input[placeholder*="Tax" i]',
        'input[placeholder*="Search" i]',
        'input[type="search"]',
        'input[type="text"]',
    ]

    # If there are tabs for search modes, try switching to ID-based tab
    try_click(
        page,
        [
            page.get_by_role("tab", name=re.compile("เลข|ID|Registration|Tax", re.I)),
            page.get_by_role("button", name=re.compile("เลข|ID|Registration|Tax", re.I)),
        ],
        timeout_ms=1200,
    )

    # Prefer accessible role by label if present
    try:
        labeled = page.get_by_label(re.compile("ค้นหา|นิติบุคคล|เลข|Juristic|Registration|Search", re.I))
        if labeled.first.is_visible():
            search_input = labeled.first
        else:
            search_input = first_visible(page, input_selectors, timeout_ms=5000)
    except Exception:
        search_input = first_visible(page, input_selectors, timeout_ms=5000)

    # Broaden fallback: any visible text input
    if not search_input:
        try:
            search_input = page.locator('input:visible').first
            if not search_input.is_visible():
                search_input = None
        except Exception:
            search_input = None
    if not search_input:
        try:
            search_input = page.locator('mat-form-field input').first
            if not search_input.is_visible():
                search_input = None
        except Exception:
            search_input = None

    if not search_input:
        # Debug aids
        if verbose:
            try:
                page.screenshot(path="debug_search_page.png", full_page=True)
                with open("debug_search_page.html", "w", encoding="utf-8") as f:
                    f.write(page.content())
            except Exception:
                pass
        raise RuntimeError("Could not find search input on page")

    if verbose:
        print("Typing juristic ID into search box...", file=sys.stderr)
    search_input.fill(juristic_id)

    # Try to submit: press Enter or click a search button
    search_input.press("Enter")
    # Also try click a button to be safe
    # Prefer the main search icon/button near the #form
    button_variants = [
        '#searchicon',
        page.get_by_role("button", name=re.compile("ค้นหา|search|Search", re.I)),
        'button[type="submit"]',
        'button[id*="search"]',
    ]
    try_click(page, button_variants, timeout_ms=2000)
    # Try pick first suggestion if an autocomplete list appears
    try:
        suggestion = page.get_by_text(juristic_id, exact=False).first
        if suggestion.is_visible():
            suggestion.click()
    except Exception:
        try:
            page.locator("li[role='option']").first.click(timeout=1200)
        except Exception:
            pass


def wait_for_results(page: Page, juristic_id: str, verbose: bool = False) -> Optional[Any]:
    # Try to find a result item containing the juristic id or a result list/grid
    potential_results = [
        page.get_by_role("link", name=re.compile(juristic_id)),
        'a:has-text("%s")' % juristic_id,
        '[data-testid*="result" i]',
        '.results, #results, [class*="result" i]',
        'table, ul[role="list"], div[role="list"]',
        'mat-table, .mat-table, [role="table"]',
        '[role="row"], .mat-row, tr',
    ]

    # Wait for navigation or content change
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except PlaywrightTimeoutError:
        pass

    for attempt in range(2):
        for pr in potential_results:
            try:
                locator = page.locator(pr) if isinstance(pr, str) else pr
                locator.first.wait_for(state="visible", timeout=3000)
                if verbose:
                    print(f"Found results via selector: {pr}", file=sys.stderr)
                return locator
            except Exception:
                continue
        # small wait and try again
        time.sleep(1)
    # Debug aid on failure
    if verbose:
        try:
            page.screenshot(path="debug_results_page.png", full_page=True)
            with open("debug_results_page.html", "w", encoding="utf-8") as f:
                f.write(page.content())
        except Exception:
            pass
    return None


def open_first_result(page: Page, result_locator: Any, verbose: bool = False) -> bool:
    # If the locator itself is a link, click it. Otherwise, try to find first link inside it.
    try:
        # Prefer an item that looks like a result card/link
        first_link = None
        try:
            if result_locator.get_by_role:
                first_link = result_locator.get_by_role("link").first
        except Exception:
            pass
        if not first_link:
            first_link = result_locator.locator('a').first
        if first_link.is_visible():
            if verbose:
                print("Opening first result...", file=sys.stderr)
            first_link.click()
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            return True
    except Exception:
        pass
    # As a fallback, try clicking a row-like element
    try:
        row = page.locator('[role="row"], .mat-row, tr').first
        if row.is_visible():
            row.click()
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            return True
    except Exception:
        pass
    # As a final fallback, try clicking the locator itself
    try:
        result_locator.first.click()
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        return True
    except Exception:
        return False


def extract_text_candidates(page: Page, selectors: List[str]) -> Optional[str]:
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if loc.first.is_visible():
                text = loc.first.inner_text().strip()
                if text:
                    return text
        except Exception:
            continue
    return None


def extract_details(page: Page) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "url": page.url,
        "title": None,
        "name_th": None,
        "name_en": None,
        "status": None,
        "address": None,
        "registered_capital": None,
        "directors": [],
        "raw_text_sample": None,
    }

    # Title / Name candidates
    data["title"] = extract_text_candidates(page, [
        "h1",
        "h2",
        '[data-testid*="title" i]',
        '[data-testid*="name" i]',
    ])

    # Name TH and EN heuristics
    name_th = extract_text_candidates(page, [
        'xpath=//*[contains(text(),"ชื่อ") and contains(text(),"ไทย")]/following::*[1]',
        'xpath=//*[contains(text(),"ชื่อนิติบุคคล")]/following::*[1]',
    ])
    name_en = extract_text_candidates(page, [
        'xpath=//*[contains(text(),"ชื่อ") and contains(text(),"อังกฤษ")]/following::*[1]',
        'xpath=//*[contains(text(),"Name") and contains(text(),"(English")]/following::*[1]',
    ])
    data["name_th"] = name_th
    data["name_en"] = name_en

    # Status
    data["status"] = extract_text_candidates(page, [
        'xpath=//*[contains(text(),"สถานะ")]/following::*[1]',
        'xpath=//*[contains(text(),"Status")]/following::*[1]',
    ])

    # Address
    data["address"] = extract_text_candidates(page, [
        'xpath=//*[contains(text(),"ที่ตั้ง") or contains(text(),"ที่อยู่")]/following::*[1]',
        'xpath=//*[contains(text(),"Address")]/following::*[1]',
    ])

    # Registered capital
    data["registered_capital"] = extract_text_candidates(page, [
        'xpath=//*[contains(text(),"ทุน") and contains(text(),"จดทะเบียน")]/following::*[1]',
        'xpath=//*[contains(text(),"Registered") and contains(text(),"capital")]/following::*[1]',
    ])

    # Directors list heuristic: look for a list under "กรรมการ"
    try:
        directors_section = page.locator('xpath=//*[contains(text(),"กรรมการ")]/following::*[1]')
        if directors_section.first.is_visible():
            names = directors_section.first.locator('li, p, div').all_text_contents()
            cleaned = [n.strip() for n in names if n.strip()]
            # Keep up to a reasonable count
            data["directors"] = cleaned[:20]
    except Exception:
        pass

    # Raw text sample as fallback context
    try:
        body_text = page.locator('main').inner_text()
    except Exception:
        try:
            body_text = page.locator('body').inner_text()
        except Exception:
            body_text = None
    if body_text:
        data["raw_text_sample"] = " ".join(body_text.split())[:4000]

    return data


def goto_financials_tab(page: Page, verbose: bool = False) -> bool:
    # Try clicking the financials tab/link and wait for content container
    try:
        if verbose:
            print("Opening financials tab...", file=sys.stderr)
        # Open parent financial section tab first, then the subtab
        try_click(page, ['#menu2', page.get_by_text(re.compile('ข้อมูลงบการเงิน'))], timeout_ms=1500)
        # Prefer explicit subtab id
        if not try_click(page, ['#menu22'], timeout_ms=2000):
            try_click(page, [
                page.get_by_role("link", name=re.compile("งบการเงิน|Financial", re.I)),
                page.get_by_text(re.compile("งบการเงิน|Financial", re.I)),
            ], timeout_ms=2500)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeoutError:
            pass
        # Wait for AJAX-loaded content to appear
        container = page.locator('#companyProfileTab22, .tab22')
        container.wait_for(state="visible", timeout=15000)
        # Wait until the container has content/text
        try:
            page.wait_for_function("el => el && el.innerText && el.innerText.length > 50", arg=container, timeout=15000)
        except Exception:
            pass
        # Wait until a table renders
        for _ in range(30):
            if container.locator('table').count() > 0 and container.locator('table').first.is_visible():
                return True
            time.sleep(0.5)
        # Debug dump if tables not found
        try:
            with open("debug_financials_tab.html", "w", encoding="utf-8") as f:
                f.write(container.inner_html())
            page.screenshot(path="debug_financials_tab.png", full_page=True)
        except Exception:
            pass
        return False
    except Exception:
        return False


def _clean_number(text: str) -> Optional[float]:
    if text is None:
        return None
    s = text.strip()
    if not s:
        return None
    # Handle parentheses negatives
    neg = False
    if s.startswith('(') and s.endswith(')'):
        neg = True
        s = s[1:-1]
    # Remove non-numeric except dot and minus
    s = re.sub(r"[^0-9\.-]", "", s)
    if s in ("", "-", "."):
        return None
    try:
        val = float(s)
        return -val if neg else val
    except Exception:
        return None


def parse_financials_table_detailed(page: Page, verbose: bool = False) -> Dict[str, Any]:
    """Parse the multi-year financial table that shows per-year Amount and % Change.

    Returns a dict shape:
    {
      "unit": "บาท" | None,
      "years": ["2563", ...],
      "rows": [
        {"label": "สินทรัพย์รวม", "2563": {"amount": 123.0, "pct_change": -3.4}, ...}
      ]
    }
    If the expected table isn't found, returns an empty structure.
    """
    container = page.locator('#companyProfileTab22, .tab22')
    tables = container.locator('table').all()

    # Helper to find unit (e.g., "หน่วย : บาท") within the container vicinity
    unit = None
    try:
        text_block = container.inner_text()
        m = re.search(r"หน่วย\s*[:：]\s*([^\n]+)", text_block)
        if m:
            unit_raw = m.group(1).strip()
            # Remove trailing year tokens accidentally captured
            unit = re.split(r"\s+(?=(?:20|25)\d{2})", unit_raw)[0].strip()
    except Exception:
        pass

    target_table = None
    years: List[str] = []
    # Identify the table by header containing years and subheaders "จำนวนเงิน" and "%เปลี่ยนแปลง"
    for t in tables:
        try:
            if not t.is_visible():
                continue
            thead_rows = t.locator('thead tr').all()
            headers_txt = [" ".join(r.locator('th,td').all_text_contents()) for r in thead_rows]
            has_sub = any('จำนวนเงิน' in h and '%เปลี่ยนแปลง' in h for h in headers_txt)
            # Extract years that look like 25xx or 20xx
            yrs = []
            for r in thead_rows:
                cells = [c.strip() for c in r.locator('th,td').all_text_contents()]
                for c in cells:
                    if re.search(r"^(20\d{2}|25\d{2})$", c):
                        yrs.append(c)
            if has_sub and yrs:
                target_table = t
                years = yrs
                break
        except Exception:
            continue

    if not target_table or not years:
        return {"unit": unit, "years": [], "rows": []}

    # Parse body rows; each row has label + for each year: amount, pct
    rows_out: List[Dict[str, Any]] = []
    body_rows = target_table.locator('tbody tr').all()
    for r in body_rows:
        try:
            cells = [c.strip() for c in r.locator('th,td').all_text_contents()]
            if len(cells) < 1 + 2 * len(years):
                # Skip subtotal separators or malformed
                continue
            label = cells[0]
            entry: Dict[str, Any] = {"label": label}
            # Iterate pairs for each year
            idx = 1
            for y in years:
                amount_txt = cells[idx] if idx < len(cells) else ''
                pct_txt = cells[idx + 1] if (idx + 1) < len(cells) else ''
                amount = _clean_number(amount_txt)
                pct = _clean_number(pct_txt)
                entry[y] = {"amount": amount, "pct_change": pct}
                idx += 2
            rows_out.append(entry)
        except Exception:
            continue

    return {"unit": unit, "years": years, "rows": rows_out}


def is_detail_page(page: Page, juristic_id: str) -> bool:
    try:
        if page.get_by_text(juristic_id, exact=False).first.is_visible():
            return True
    except Exception:
        pass
    try:
        if page.get_by_text(re.compile("ชื่อนิติบุคคล|เลขทะเบียนนิติบุคคล")).first.is_visible():
            return True
    except Exception:
        pass
    return False


def scrape(juristic_id: str, headless: bool = False, slow_mo: int = 0, verbose: bool = False) -> Dict[str, Any]:
    with sync_playwright() as p:
        # Try using system Chrome to reduce bot detection, fallback to bundled Chromium
        browser = None
        try:
            browser = p.chromium.launch(channel="chrome", headless=headless, slow_mo=slow_mo,
                                        args=["--disable-blink-features=AutomationControlled"])  # type: ignore
        except Exception:
            browser = p.chromium.launch(headless=headless, slow_mo=slow_mo,
                                        args=["--disable-blink-features=AutomationControlled"])  # type: ignore

        ua = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/119.0.0.0 Safari/537.36"
        )
        context = browser.new_context(
            locale="th-TH",
            user_agent=ua,
            viewport={"width": 1366, "height": 768},
        )
        # Reduce automation fingerprints
        context.add_init_script(
            """
            // Remove webdriver flag
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            // Mock plugins and languages
            Object.defineProperty(navigator, 'languages', { get: () => ['th-TH','en-US','en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            // Permissions query spoof
            const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
            if (originalQuery) {
              window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ? Promise.resolve({ state: Notification.permission }) : originalQuery(parameters)
              );
            }
            """
        )
        page = context.new_page()
        page.set_default_timeout(15000)

        if verbose:
            print(f"Navigating to {SEARCH_URL} ...", file=sys.stderr)
        page.goto(SEARCH_URL, wait_until="domcontentloaded")

        accept_cookies(page)

        fill_search_and_submit(page, juristic_id, verbose=verbose)

        # Some searches navigate directly to a detail page
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except PlaywrightTimeoutError:
            pass
        if is_detail_page(page, juristic_id):
            # On the detail page, go to financials and parse only the table
            if goto_financials_tab(page, verbose=verbose):
                table = parse_financials_table_detailed(page, verbose=verbose)
                context.close()
                browser.close()
                return {"financials_table": table}
            context.close()
            browser.close()
            raise RuntimeError("Could not open financials tab on detail page")

        # Wait for results and open first detail page
        result_locator = wait_for_results(page, juristic_id, verbose=verbose)
        if not result_locator:
            raise RuntimeError("Search results not found or page structure changed.")

        opened = open_first_result(page, result_locator, verbose=verbose)
        if not opened:
            # Attempt to stay on results and parse the first visible card/table row
            if verbose:
                print("Could not open details; extracting from results page...", file=sys.stderr)
            details = extract_details(page)
            details["note"] = "Extracted from results page; detail click failed"
            return details

        # On the detail page, parse only the financials table
        if goto_financials_tab(page, verbose=verbose):
            table = parse_financials_table_detailed(page, verbose=verbose)
            context.close()
            browser.close()
            return {"financials_table": table}

        context.close()
        browser.close()
        raise RuntimeError("Could not open financials tab after navigating to detail page")


def main():
    parser = argparse.ArgumentParser(description="Scrape DBD Data Warehouse by juristic ID (outputs financial table JSON)")
    parser.add_argument("juristic_id", help="13-digit juristic ID to search")
    # WAF note: default to headful; allow explicit headless opt-in (optional for dev/CI)
    mgroup = parser.add_mutually_exclusive_group()
    mgroup.add_argument("--headless", action="store_true", help="Run in headless mode (may be blocked by WAF)")
    mgroup.add_argument("--headful", action="store_true", help="Run in headful mode (default)")
    parser.add_argument("--slow", type=int, default=0, help="Slow motion in ms for debugging")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging to stderr")

    args = parser.parse_args()

    if not is_valid_juristic_id(args.juristic_id):
        print("Error: juristic_id must be exactly 13 digits.", file=sys.stderr)
        sys.exit(2)

    try:
        # Default to headful unless explicitly requested headless
        effective_headless = True if args.headless else False
        data = scrape(
            juristic_id=args.juristic_id,
            headless=effective_headless,
            slow_mo=args.slow,
            verbose=args.verbose,
        )
    except Exception as e:
        print(json.dumps({
            "juristic_id": args.juristic_id,
            "error": str(e),
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    data["juristic_id"] = args.juristic_id

    # Always output the detailed financials table JSON by default
    output_data = data.get("financials_table", {"unit": None, "years": [], "rows": []})
    output = json.dumps(output_data, ensure_ascii=False, indent=2)

    # Ensure output directory exists and write file named by juristic id
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"{args.juristic_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(output)

    # Print a one-line confirmation with path
    print(out_path)


if __name__ == "__main__":
    main()
