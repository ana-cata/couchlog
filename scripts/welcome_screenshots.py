"""Takes the five small pictures on the welcome page (docs/welcome.md), from a demo copy of Couchlog.

The pictures show the demo's sample titles, never anyone's real history. Run a demo copy with its own database first,
then this script, as docs/welcome.md explains:

    uv run python scripts/welcome_screenshots.py http://127.0.0.1:8766

It presses Try the demo, opens each page at phone width and saves a picture of one part of it in
core/static/core/welcome/. Uses Playwright, which the tests already need.
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / 'core' / 'static' / 'core' / 'welcome'
GAP = 12  # pixels of page kept above and below the part shown

# (file, address, words typed in the search box or None, the first part shown, the last part shown)
PICTURES = [
    ('1-search.jpg', '/search/', 'Dune', 'form[role=search]', '.results li:nth-child(2)'),
    ('2-to-watch.jpg', '/movie/27205/', None, '.title-poster', 'h1'),  # Inception, not on the sample lists
    ('3-watched.jpg', '/series/95396/?season=1', None, '#season-1 summary', '#season-1 .episodes li:nth-child(5)'),
    ('4-series-tabs.jpg', '/series/watching/', None, 'h1', '.results li:nth-child(2)'),
    ('5-home.jpg', '/', None, 'h1', '.up-next li:nth-child(1)'),
]


def main(base):
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, timezone_id='Europe/Lisbon')
        page = context.new_page()
        page.goto(base + '/login/')
        page.click('text=Try the demo')
        page.wait_for_url('**/welcome/', timeout=120_000)

        for name, address, typed, first, last in PICTURES:
            page.goto(base + address)
            if typed:
                page.fill('input[type=search]', typed)
                page.wait_for_selector('.results li:nth-child(2) img')
            page.wait_for_load_state('networkidle')
            top = page.locator(first).first.bounding_box()['y'] - GAP
            bottom = (box := page.locator(last).first.bounding_box())['y'] + box['height'] + GAP
            page.screenshot(
                path=OUT / name, type='jpeg', quality=70, full_page=True,
                clip={'x': 0, 'y': top, 'width': 390, 'height': bottom - top},
            )
            print('saved', OUT / name)
        browser.close()


if __name__ == '__main__':
    main(sys.argv[1].rstrip('/') if len(sys.argv) > 1 else 'http://127.0.0.1:8766')
