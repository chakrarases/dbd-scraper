# Repository Guidelines

## Project Structure & Module Organization
- `scrape_dbd_playwright.py`: Main Playwright scraper. Contains CLI, navigation, extraction, and financials parsing.
- `requirements.txt`: Python dependencies (Playwright).
- `README.md`: Quick start and usage examples.
- `debug_*.html/png`: Saved pages and screenshots for troubleshooting; safe to delete.

Keep new modules small and focused. Prefer adding helpers inside `scrape_dbd_playwright.py` only if tightly related; otherwise create new files with clear names (e.g., `selectors.py`, `parsers.py`).

## Build, Test, and Development Commands
- Install deps: `pip install -r requirements.txt`
- Install browser binaries: `python -m playwright install chromium`
- Run scrape: `python scrape_dbd_playwright.py 0105555017760`
- Debug run: `python scrape_dbd_playwright.py <ID> --headful --slow 100 -v`
- Output: writes JSON to `data/<ID>.json` and prints the path

Use headful + slow motion when adjusting selectors; commit only code, not large debug artifacts.

## Coding Style & Naming Conventions
- Language: Python 3.9+. Indentation: 4 spaces. Line length ~100.
- Names: `snake_case` for functions/vars, `UPPER_SNAKE_CASE` for constants, descriptive module names.
- Types: Use `typing` hints for public functions and return values (existing code uses them).
- Logging: Write developer logs to `stderr` behind `--verbose`.
- Optional formatting: Prefer `black` and `ruff` locally if installed; no enforced config yet.

## Testing Guidelines
- Framework: None required today. Prefer lightweight smoke tests:
  - Known-good ID: `python scrape_dbd_playwright.py 0105555017760 -v` and verify `data/<ID>.json` exists.
  - Validate output: open the JSON and confirm `years` is non-empty and rows contain `amount` and `pct_change` fields.
- If adding tests, use `pytest`, place files under `tests/` and name `test_*.py`.

## Commit & Pull Request Guidelines
- Commits: Small, focused, present tense. Suggested prefixes: `feat:`, `fix:`, `chore:`, `docs:`.
- PRs must include:
  - Summary of change and rationale (DOM changes, selector updates, etc.).
  - Reproduction steps and sample command(s).
  - Before/after evidence (JSON snippet or screenshot if UI-driven).
  - Any impacts on CLI flags or output shape.

## Security & Configuration Tips
- Do not store secrets; this scraper uses public data. Respect site terms and rate limits.
- Prefer `--headful` during selector work; run headless in automation.
- If the DOM changes, update selector lists conservatively and keep fallbacks.
- Large HTML/PNG debug files should not be committed unless essential for review.
