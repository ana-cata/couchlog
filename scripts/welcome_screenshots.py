"""Takes the small pictures on the welcome page (docs/welcome.md), from a demo copy of Couchlog.

The pictures show the demo's sample titles, never anyone's real history. Each picture has numbered red arrows that
point at what you can press; the numbers match the list under the picture on the welcome page. Run a demo copy with
its own database first, then this script, as docs/welcome.md explains:

    uv run python scripts/welcome_screenshots.py http://127.0.0.1:8766

It presses Try the demo, opens each page at phone width, draws the arrows on it and saves a picture of one part of it
in core/static/core/welcome/. It also writes each picture's size into welcome.html, so the page keeps room for it while
it loads. Uses Playwright, which the tests already need.
"""

import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'core' / 'static' / 'core' / 'welcome'
PAGE = ROOT / 'core' / 'templates' / 'core' / 'welcome.html'
WIDTH = 390  # a phone's width, in the page's pixels
GAP = 12  # pixels of page kept around the part shown
RED = '#ff3b3b'  # the arrows' red, the one exception to the palette (Identity/identity.md)
NAVY = '#0a192f'

# Each picture: the file, the address, the words typed in the search box (or None), the first and last part of the
# page shown, and its arrows. An arrow is (number, what it points at, the side it comes from, where along that side
# from 0 to 1, how long). "words:" before a selector points at the words inside it, not the whole box (a title's box
# is as wide as its tile). The picture always grows to keep every arrow whole.
PICTURES = [
    ('1-search.jpg', '/search/', 'Dune', 'h1', '.results li:nth-child(1)', [
        (1, 'form[role=search]', 'top', 0.62, 40),
        (2, '.results li:nth-child(1) .corner-button', 'left', 0.5, 40),
        (3, 'words:.results li:nth-child(1) strong', 'right', 0.5, 40),
    ]),
    ('2-to-watch.jpg', '/movie/27205/', None, '.title-poster', 'h1', [  # Inception, not on the sample lists
        (1, 'button:has-text("Add to To Watch")', 'right', 0.5, 44),
    ]),
    ('3-movie.jpg', '/movie/278/', None, '.rating-section', 'button:has-text("Mark as not watched")', [  # watched once
        (1, 'words:.rating-section :text("Rate it or add a note")', 'right', 0.5, 44),
        (2, '.watched-form input[type=date]', 'top', 0.85, 34),
        (3, '.watched-form button', 'top', 0.5, 40),
        (4, 'words:.watched-form label:has(input[type=checkbox])', 'right', 0.5, 40),
        (5, 'button:has-text("Mark as not watched")', 'top', 0.5, 36),
    ]),
    ('4-series-top.jpg', '/series/95396/', None, '.series-bar', 'button:has-text("Stop watching")', [  # Severance
        (1, 'button:has-text("Stop watching")', 'right', 0.5, 44),
    ]),
    ('5-series-seasons.jpg', '/series/95396/?season=1', None, '#season-1 summary', '#season-1 .episodes li:nth-child(6)', [
        (2, '#season-1 summary', 'top', 0.62, 36),
        (3, '#season-1 .season-action button', 'right', 0.5, 44),
        (4, '#season-1 .episodes li:nth-child(6) button.check', 'left', 0.5, 44),
        (5, '#season-1 .episodes li:nth-child(4) .take-back', 'left', 0.5, 44),
    ]),
    ('6-lists.jpg', '/series/watching/', None, 'h1', '.results li:nth-child(1)', [
        (1, 'nav.tabs a:has-text("Finished")', 'top', 0.5, 40),
        (2, 'words:.results li:nth-child(1) strong', 'right', 0.5, 40),
    ]),
    ('7-home.jpg', '/', None, 'h1', '.up-next li:nth-child(1)', [
        (1, '.news li:nth-child(1)', 'bottom', 0.5, 40),
        (2, '.up-next li:nth-child(1) .up-next-info a', 'right', 0.5, 40),
        (3, '.up-next li:nth-child(1) button.check', 'top', 0.5, 36),
    ]),
    ('8-calendar.jpg', '/calendar/', None, 'h2', '.calendar >> nth=1', [
        (1, 'words:.calendar-info a >> nth=0', 'right', 0.5, 40),
    ]),
    ('9-profile.jpg', '/profile/', None, '.time-spent', 'button:has-text("Log out")', [
        (1, 'select', 'top', 0.75, 40),
        (2, 'words:button:has-text("Save time zone")', 'right', 0.5, 44),
        (3, 'words:button:has-text("Log out")', 'right', 0.5, 44),
    ]),
]

# Draws one arrow on the page, in the page's own coordinates, so it scrolls with what it points at.
DRAW = """([n, head, tail]) => {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('style', 'position:absolute;left:0;top:0;overflow:visible;pointer-events:none;z-index:1000');
  svg.setAttribute('width', '1'); svg.setAttribute('height', '1');
  const [hx, hy] = head, [tx, ty] = tail, len = Math.hypot(hx - tx, hy - ty) || 1;
  const ux = (hx - tx) / len, uy = (hy - ty) / len, r = 11;
  const parts = [];
  if (len > r + 10) {
    const sx = tx + ux * r, sy = ty + uy * r, bx = hx - ux * 9, by = hy - uy * 9;
    parts.push(`<line x1="${sx}" y1="${sy}" x2="${bx}" y2="${by}" stroke="${NAVY}" stroke-width="6"/>`);
    parts.push(`<line x1="${sx}" y1="${sy}" x2="${bx}" y2="${by}" stroke="${RED}" stroke-width="3"/>`);
    const px = -uy * 6, py = ux * 6;
    parts.push(`<polygon points="${hx},${hy} ${bx + px},${by + py} ${bx - px},${by - py}" fill="${RED}" stroke="${NAVY}" stroke-width="1"/>`);
  }
  parts.push(`<circle cx="${tx}" cy="${ty}" r="${r}" fill="${RED}" stroke="${NAVY}" stroke-width="2"/>`);
  parts.push(`<text x="${tx}" y="${ty + 4.5}" text-anchor="middle" font-family="system-ui, sans-serif" font-size="13" font-weight="700" fill="#fff">${n}</text>`);
  svg.innerHTML = parts.join('');
  document.body.appendChild(svg);
}""".replace('${NAVY}', NAVY).replace('${RED}', RED)

OUTWARD = {'top': (0, -1), 'bottom': (0, 1), 'left': (-1, 0), 'right': (1, 0)}


def box_of(page, selector):
    """Where a part of the page is, in the page's own coordinates (not the window's). With "words:" in front, where
    the words inside it are."""
    words = selector.startswith('words:')
    element = page.locator(selector.removeprefix('words:')).first
    x, y, w, h = element.evaluate(
        """(el, words) => {
          let box = el.getBoundingClientRect();
          if (words) { const range = document.createRange(); range.selectNodeContents(el); box = range.getBoundingClientRect(); }
          return [box.x + window.scrollX, box.y + window.scrollY, box.width, box.height];
        }""",
        words,
    )
    return x, y, w, h


def arrow_points(box, side, at, length):
    """The arrow's head, on the given side of the box, and its tail (the numbered circle), `length` further out."""
    x, y, w, h = box
    head = {
        'top': (x + w * at, y - 2),
        'bottom': (x + w * at, y + h + 2),
        'left': (x - 2, y + h * at),
        'right': (x + w + 2, y + h * at),
    }[side]
    dx, dy = OUTWARD[side]
    reach = max(length, 14)  # with length 0 the circle sits right next to the box, with no line
    return head, (head[0] + dx * reach, head[1] + dy * reach)


def write_size(name, width, height):
    """Puts the picture's size (in the page's pixels) on its <img> in welcome.html, in place of the old one."""
    html = PAGE.read_text(encoding='utf-8')
    tag = re.search(rf'<img [^>]*welcome/{re.escape(name)}[^>]*>', html).group(0)
    sized = re.sub(r' (width|height)="\d+"', '', tag).replace('<img ', f'<img width="{width}" height="{height}" ', 1)
    PAGE.write_text(html.replace(tag, sized), encoding='utf-8', newline='')


def main(base):
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={'width': WIDTH, 'height': 844}, device_scale_factor=2, timezone_id='Europe/Lisbon'
        )
        page = context.new_page()
        page.goto(base + '/login/')
        page.click('text=Try the demo')
        page.wait_for_url('**/welcome/', timeout=120_000)

        for name, address, typed, first, last, arrows in PICTURES:
            page.goto(base + address)
            if typed:
                page.fill('input[type=search]', typed)
                page.wait_for_selector('.results li:nth-child(2) img')
            page.wait_for_load_state('networkidle')
            top = box_of(page, first)[1]
            last_box = box_of(page, last)
            bottom = last_box[1] + last_box[3]
            for number, selector, side, at, length in arrows:
                head, tail = arrow_points(box_of(page, selector), side, at, length)
                page.evaluate(DRAW, [number, head, tail])
                top, bottom = min(top, tail[1] - 13), max(bottom, tail[1] + 13)
            height = round(bottom - top + 2 * GAP)
            page.screenshot(
                path=OUT / name,
                type='jpeg',
                quality=70,
                full_page=True,
                clip={'x': 0, 'y': top - GAP, 'width': WIDTH, 'height': height},
            )
            write_size(name, WIDTH, height)
            print('saved', OUT / name)
        browser.close()


if __name__ == '__main__':
    main(sys.argv[1].rstrip('/') if len(sys.argv) > 1 else 'http://127.0.0.1:8766')
