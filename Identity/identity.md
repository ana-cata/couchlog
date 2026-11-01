# Couchlog identity

How Couchlog looks: the logo, the colours and where each one goes. The logo files are in this folder. When a card changes how the app looks, it follows this page.

## The logo

**The main logo is the hot pink wordmark** (`logoCouchlog_hotpink.svg`). Everything else is a variation of it.

| File | What it is | Where it goes |
|---|---|---|
| `logoCouchlog_hotpink.svg` | **Main logo.** Hot pink `#e764bb`. | Header of the app, login page, anywhere the logo appears on navy. |
| `logoCouchlog_lightpink.svg` | Variation. Light pink `#ffb3d9`. | A quieter place where the main logo would be too loud (for example the footer or the About page). Only on navy. |
| `logoCouchlog_small_square.svg` | Variation. Just the couch, in a square. | Browser tab icon and phone home screen icon, on a navy rounded square. |
| `logoCouchlog_image.svg` | The whole presentation board with the palette. | Reference only. Never used in the app. |

Rules for every logo:
- Never stretch it. Scale it evenly.
- Keep clear space around it of at least the height of the "C" loop.
- Do not recolour it. Only the colours in the palette below.
- Do not add a shadow, outline or background to the wordmark itself.
- Smallest size for the wordmark: about 100 px wide. Below that, use the couch icon.
- The TMDB logo on the About page stays smaller than ours. That is a TMDB rule and also design rule 4 in plan.md.

## The colours

| Name | Hex | Used for | Contrast on navy |
|---|---|---|---|
| Navy | `#0a192f` | The background of every page. | |
| Off-white | `#fef7f7` | Normal text. | 16.6 : 1 |
| Hot pink | `#e764bb` | Titles, links, buttons, the main logo. | 5.8 : 1 |
| Light pink | `#ffb3d9` | Small accents (see below). | 10.6 : 1 |

(Contrast says how easy text is to read on the background. Anything above 4.5 is comfortable for normal text.)

### The app is dark only
- Every page has the navy background, always. It does not switch to a light version when the computer is set to light mode.
- Off-white is only a text colour. It is never a page background.

### Where each colour goes
- **Page background:** navy.
- **Normal text:** off-white.
- **Titles (h1, h2, h3):** hot pink.
- **Links:** hot pink and **always underlined**. Colour alone is not enough to tell a link from normal text, because hot pink and off-white are close in brightness (only 2.9 : 1 between them). The underline fixes that.
- **Buttons:** hot pink background with **navy text**. Not white text: white on hot pink is too faint (2.9 : 1), navy on hot pink is fine (5.8 : 1).
- **Light pink** is for small, soft accents only. Suggested uses:
  - a link when the mouse is over it (hover),
  - small labels and extra info such as dates and counts,
  - progress bars
- Light pink is **not** for whole paragraphs or titles. If everything is pink, nothing stands out.

### Only these four colours
- There is no second navy. Cards, search boxes and tables use the same navy as the page.
- They are told apart from the page by a thin line (1 px) in off-white at low opacity (about 20%), not by a different background.
- The only colours outside the palette are the grey and the green of the round check button (see below).

## What this means for the app today
- The header now shows the text "Couchlog". It becomes the main logo (hot pink), linking to the home page.
- The browser tab gets the couch icon.
- The About page keeps the TMDB logo and notice, smaller than ours.
- The round check button on episodes keeps its grey `#8b93a0` (not watched) and green `#2e7d32` (watched). They are not in the palette, and that is on purpose: they say "done" and "not done" clearly.

## For the card that builds it
- The app uses Pico CSS. It already has colour settings (variables) that can be overridden in `couchlog.css`: `--pico-background-color`, `--pico-color`, `--pico-h1-color` (and h2 to h6), `--pico-primary` (links), `--pico-primary-background` and `--pico-primary-inverse` (buttons), `--pico-primary-hover`, `--pico-primary-underline`, `--pico-muted-color`. Cards and inputs: set their background variables (`--pico-card-background-color`, `--pico-form-element-background-color`) to navy and their border variables (`--pico-muted-border-color`) to the thin off-white line.
- Make the app dark only by putting `data-theme="dark"` on the `<html>` tag in `base.html`. Without it, Pico follows the computer's light or dark setting.
- Copy the final logo files into `core/static/core/` and use them from there. The files in this folder stay as the originals.
- The favicon is made from the square couch icon on a navy rounded square, with a thicker line than the original so it still reads at 16 and 32 px. The icon file does not need to change for that.
- The tests do not check colours. Check the pages by eye in the browser, at phone width as well.

## Decided (2026-11-01)
- The four colours are the whole palette. No extra panel navy.
- The check button keeps its grey and green.
- The couch icon (`logoCouchlog_small_square.svg`) is approved as it is.
