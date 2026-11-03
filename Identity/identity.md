# Couchlog identity

How Couchlog looks: the logo, the colours and where each one goes. The logo files are in this folder. When a card changes how the app looks, it follows this page.

## The logo

**The main logo is the hot pink wordmark** (`logoCouchlog_hotpink.svg`). Everything else is a variation of it.

| File | What it is | Where it goes |
|---|---|---|
| `logoCouchlog_hotpink.svg` | **Main logo.** Hot pink `#e764bb`. | Header of the app, login page, anywhere the logo appears on navy. |
| `logoCouchlog_lightpink.svg` | Variation. Light pink `#ffb3d9`. | A quieter place where the main logo would be too loud (for example the footer or the About page). Only on navy. |
| `logoCouchlog_small_square.svg` | Variation. Just the couch, in a square. | Browser tab icon and phone home screen icon, on navy (see "What this means for the app today"). |
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
| Off-white | `#fef7f7` | Text, and the quiet buttons and menu (softened, see below). | 16.6 : 1 |
| Hot pink | `#e764bb` | The main logo, the page title, the page you are on, links inside text, and anything the mouse is over. | 5.8 : 1 |
| Light pink | `#ffb3d9` | The main buttons and small accents (see below). | 10.6 : 1 |

(Contrast says how easy text is to read on the background. Anything above 4.5 is comfortable for normal text.)

### The app is dark only
- Every page has the navy background, always. It does not switch to a light version when the computer is set to light mode.
- Off-white is only a text colour. It is never a page background.

### Where each colour goes
The rule: **pink means "you are here" or "you can press this". Everything else is off-white.** (Changed on 2026-11-02, card #67: the app was too pink, so nothing stood out.)
- **Page background:** navy.
- **Normal text:** off-white.
- **Small extra info** (dates, counts, captions, the grey words under a name): off-white **softened to about 70%** (`rgba(254, 247, 247, 0.7)`, about 7 : 1 on navy). Not light pink.
- **Titles:** only the page title (h1) is hot pink. The smaller headings (h2 to h6) are off-white.
- **Links inside text:** hot pink and **always underlined**. Colour alone is not enough to tell a link from normal text, because hot pink and off-white are close in brightness (only 2.9 : 1 between them). The underline fixes that. (The menu and the tabs are the exception: see "The menu" below.)
- **Main buttons** (the solid ones: Search, Log in, Save, Mark as watched ...): **light pink background with navy text**, and **hot pink when the mouse is over them**. Navy on light pink is 10.6 : 1, navy on hot pink 5.8 : 1. Not white text: white on hot pink is too faint (2.9 : 1). A phone has no mouse, so the light pink has to look right on its own.
- **Quiet buttons** (the outlined ones: Remove, Undo, Stop watching, the season buttons ...): a thin **softened off-white outline and text**, and **hot pink outline and text when the mouse is over them**.
- **Light pink** is also for small, soft accents: a link when the mouse is over it, and progress bars.
- Pink is **not** for whole paragraphs or titles, and a page has one main button at most. If everything is pink, nothing stands out.

### The menu and the tabs
- The header is a **bar** across the full width, with a thin line under it (the 20% line). The logo is on the left, the menu on the right. It stays at the top while the page scrolls. On a phone the menu items drop to a second row.
- The names in the menu, and in the tabs under Movies and Series, are off-white with **no underline**: where they sit already says they are links.
- The page you are on is **hot pink and bold**, with no bar under it. Not colour alone: hot pink and off-white look almost equally bright, so the bold is what tells them apart.
- Under the mouse (or when tabbed to) a name turns hot pink.

### Only these four colours
- There is no second navy. Cards, search boxes and tables use the same navy as the page.
- They are told apart from the page by a thin line (1 px) in off-white at low opacity (about 20%), not by a different background.
- The only colours outside the palette are the grey and the green of the round check button (see below).

## What this means for the app today
Built in card #48.
- The header shows the main logo (hot pink), linking to the home page (`core/static/core/logo-couchlog.svg`, a copy of `logoCouchlog_hotpink.svg`).
- The browser tab shows the couch icon (`core/static/core/favicon.svg`: the couch on a navy rounded square, with a thicker line so it still reads at 16 and 32 px).
- The phone home screen icon is the couch on a full navy square (`core/static/core/apple-touch-icon.png`, 180 × 180, linked as `apple-touch-icon` on every page). Built in card #77. It keeps the original couch line (180 px is big enough), the couch is 70% of the square's width, and the square has no rounded corners and nothing see-through, because the phone rounds the corners itself and an iPhone puts black behind see-through parts. It was made once from `logoCouchlog_small_square.svg` with a short Playwright script (draw it on navy in the browser, take a picture), so redo it the same way if the couch changes.
- Not done yet: the light pink wordmark.
- The About page keeps the TMDB logo and notice, smaller than ours.
- Quieter buttons (Remove, Undo ...) are a softened off-white outline; the main buttons are solid light pink with navy text. (Changed in card #67: they were hot pink.)
- Underlined links are the ones inside text. The names under posters stay off-white and are underlined when the mouse is over them.
- Dividers and cards use the thin line at 20%; boxes you type in use 40%, so they are easy to find.
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
