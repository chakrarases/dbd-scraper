**DBD Juristic Scraper (Playwright, Python)**

- **Purpose**: Searches https://datawarehouse.dbd.go.th/searchJuristic by a 13-digit juristic ID and extracts key details.
- **Tech**: Python + Playwright (Chromium) using the sync API.

**Setup**

- Python 3.9+
- Install deps: `pip install -r requirements.txt`
- Install browser binaries: `python -m playwright install chromium`

**Usage**

- Basic (writes JSON to `data/<ID>.json`): `python scrape_dbd_playwright.py 0105555017760`
- Headless (CI only; may be blocked by WAF): `python scrape_dbd_playwright.py 0105555017760 --headless`
- Debug selector tuning: `python scrape_dbd_playwright.py 0105555017760 --slow 100 -v`

**Output**

- Writes a financials table JSON that mirrors the site’s multi-year table (Amount + % Change) to `data/<ID>.json`.
  - Shape: `{ unit, years: [..], rows: [{ label, "2563": {amount, pct_change}, ... }] }`

**Notes**

- The site may change its DOM or apply anti-bot protections/WAF. The script includes multiple selector heuristics and fallbacks, but selectors may need periodic updates.
- Headful is the default to reduce WAF friction; use `--headless` only where a trusted environment allows it.
- If cookies/consent banners appear, the script attempts to accept them automatically.
