import csv
import asyncio
import re
import sys
import logging

from typing import Any, Dict, List, Optional

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from playwright.sync_api import Page

juristic_ids = [
    "0105542065502"
]

output_file = "dbd_data.csv"

logging.basicConfig(
    filename="dbd_scraper.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

SEARCH_URL = "https://datawarehouse.dbd.go.th/searchJuristic"


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

async def scrape_dbd_data(playwright, juristic_id, max_retries=3):
    for attempt in range(1, max_retries + 1):
        try:
            logging.info(f"Attempt {attempt}: Scraping data for juristic ID {juristic_id}")
            browser = await playwright.chromium.launch(headless=False, slow_mo=100)
            page = await browser.new_page()
            await page.goto("https://datawarehouse.dbd.go.th/index", timeout=5000)
            # Close pop-up if it appears
            try:
                await page.click("text=ปิด", timeout=5000)
                logging.info("Pop-up closed successfully.")
            except:
                logging.info("No pop-up detected or already closed.")
            
            await page.wait_for_selector("#searchText", timeout=5000)

            await page.fill("#searchText", juristic_id)
            await page.click("#btnSearch")
            await page.wait_for_selector(".table", timeout=5000)

            try:
                company_name = await page.inner_text("xpath=//table//tr[2]/td[2]")
                active_status = await page.inner_text("xpath=//table//tr[2]/td[6]")
            except Exception as e:
                logging.error(f"Error extracting data for {juristic_id}: {e}")
                company_name = "Not Found"
                active_status = "Not Found"

            await browser.close()
            return {
                "juristic_id": juristic_id,
                "company_name": company_name,
                "active_status": active_status
            }

        except PlaywrightTimeoutError as e:
            logging.warning(f"Timeout on attempt {attempt} for juristic ID {juristic_id}: {e}")
        except Exception as e:
            logging.error(f"Unexpected error on attempt {attempt} for juristic ID {juristic_id}: {e}")

    logging.error(f"Failed to scrape data for juristic ID {juristic_id} after {max_retries} attempts")
    return {
        "juristic_id": juristic_id,
        "company_name": "Error",
        "active_status": "Error"
    }

async def main():
    async with async_playwright() as playwright:
        results = []
        for juristic_id in juristic_ids:
            data = await scrape_dbd_data(playwright, juristic_id)
            results.append(data)

        with open(output_file, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=["juristic_id", "company_name", "active_status"])
            writer.writeheader()
            writer.writerows(results)

# Use this instead of asyncio.run() in interactive environments
if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())