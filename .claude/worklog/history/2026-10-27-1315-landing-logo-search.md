# Landing: Steward logo, a search pill whose list opens in a card, plan-wall wordmark

- **Author:** Claude (session with Atahan) · **Date:** 2026-10-27
- **Related:** D-027 (Steward rename), docs/product/visualization.md (Landing)

## Summary
The map landing's always-open 400 px list panel is replaced: Steward's mark and a new wordmark stand alone at the top
left, a search pill sits under them, and a click in it brings a glass card in round it with the list (animated with
clip-path / transform, not height). The new wordmark (the name as plan walls raised as low clay walls, you in the d's
doorway, "finer walls" 1.5) is one geometry file shared by the React component and the brand-SVG generator. The
picked building's "Open" is folded into its row.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | The landing shows the mark (`/brand/mark.svg`, `mark-light.svg` in light theme) and the `Wordmark` component in an `h1.ml-logo`, outside the search panel | `frontend/src/map/MapLanding.tsx` (JSX before `<aside className="ml-panel…">`) | read the JSX |
| C2 | The list opens on focus / click / typing in the field and on `/` (not while a building is open, not from inside another input); it closes on Esc (Esc clears a typed query first), the × in the field (when nothing is typed), a map click, picking a located building, and when a building opens | `MapLanding.tsx`: `listOpen`, `closeList`, the `/` keydown effect, `map.on('click')`, `pick`, the `focus` effect, the `<aside onKeyDown>` | read the code |
| C3 | Closed, the panel has no card: transparent background/border, no backdrop filter, `pointer-events: none` except the field / picked row / body; the field is its own glass pill. Open (`.ml-panel.open`), the card's glass, border, shadow and blur appear | `frontend/src/map/map.css` `.ml-panel`, `.ml-panel.open`, `.ml-top > *, .ml-body`, `.ml-field`, `.ml-panel.open .ml-field` | read the CSS |
| C4 | Opening animates `clip-path` (wide) and `transform` (narrow, `max-width: 899px`), not `height`: the panel is always full height; the closed size comes from the measured `--ml-top` (ResizeObserver on `.ml-top`, set on `<main>`) | `map.css` `.ml-panel` (clip-path inset … var(--ml-top)), the narrow media block (translateY), the `transition:` list; `MapLanding.tsx` ResizeObserver effect + `style` on `<main>` | `grep -n "transition: height" frontend/src/map/map.css` → no match; read the rules |
| C5 | Chips and the first 12 rows rise in, staggered 22 ms, when the panel opens (`--i` per row) | `map.css` `.ml-panel.open .ml-kinds`, `.ml-panel.open .ml-list li`, `@keyframes ml-rise`; `MapLanding.tsx` `style={i < 12 ? { '--i': i } …}` | read |
| C6 | No new `prefers-reduced-motion` block was added (the app runs full motion, `src/motion.ts`); the only one in map.css is the pre-existing `.ml-create` rule | `map.css` | `grep -n prefers-reduced-motion frontend/src/map/map.css` → 1 line, `.ml-create` |
| C7 | The picked building's row opens it: no separate `ml-enter` button; in the list a click on the picked row calls `onOpen`, otherwise `pick`; under the closed field `.ml-picked` is one `<button>` calling `onOpen`; both show the `GO` label ("Open ›", `.ml-go`) | `MapLanding.tsx` `GO`, the row `onClick`, `.ml-picked`; `map.css` `.ml-go`, `.ml-row-text` | `grep -n "ml-enter" frontend/src/map/MapLanding.tsx frontend/src/map/map.css` → no match |
| C8 | Narrow screens: bottom sheet at 4 px from the edges (field 16 px), open height stops clear of the logo/Account; the map controls sit above the closed sheet (from `--ml-top`) and hide while it is open (`.ml-listing`) | `map.css` `@media (max-width: 899px)` block; `MapLanding.tsx` `ml-listing` class | read |
| C9 | The wordmark geometry lives in one file, `frontend/src/brand/wordmark.json` (wall 1.5, depth 1.3, gap 3, door 4.6, 7 letters, colours), read by `Wordmark.tsx` and by `scripts/brand/marks.cjs` | `frontend/src/brand/wordmark.json`, `Wordmark.tsx` (`import WORDMARK from './wordmark.json'`), `marks.cjs` (`readFileSync(…wordmark.json)`) | read |
| C10 | `marks.cjs` now writes `wordmark.svg` / `wordmark-light.svg` from that geometry (mark + name as on the landing); every other brand SVG it writes is byte-identical to the committed ones; the wordmark SVGs contain no `<text>` | `scripts/brand/marks.cjs`, `frontend/public/brand/wordmark*.svg` | `node scripts/brand/marks.cjs /tmp/x && for f in /tmp/x/*.svg; do cmp -s $f frontend/public/brand/$(basename $f) \|\| echo DIFF $f; done` → no output (staged files = generator output); `git diff --cached --stat -- frontend/public/brand` → only the 2 wordmark files; `grep -c '<text' frontend/public/brand/wordmark.svg` → 0 |
| C11 | Type check and lint clean | `frontend/` | `cd frontend && npx tsc -b` → exit 0, no output; `npx oxlint src/map src/brand` → exit 0 |
| C12 | Docs and memory bank updated: visualization.md Landing paragraph describes logo, pill, card, animation, wordmark files; log.md has the four 2026-10-27 landing/wordmark entries; project-state.md "What exists" App line mentions the logo + search pill | the three files | read; `python3 scripts/check_links.py` → OK |

## Checks I ran
- `cd frontend && npx tsc -b; echo $?` → `tsc exit 0`
- `npx oxlint src/map src/brand; echo $?` → `oxlint exit 0`
- `python3 scripts/check_links.py` → `OK: all links resolve in 24 files`
- generator into a scratch dir, `cmp` against `frontend/public/brand/*.svg` → no DIFF lines (working files = generator output); `git diff --quiet HEAD -- frontend/public/brand/mark.svg frontend/public/brand/favicon.svg` → unchanged
- `grep -c prefers-reduced-motion frontend/src/map/map.css` → `1` (pre-existing `.ml-create`)
- `grep -c "<text" frontend/public/brand/wordmark.svg` → `0`
- Headless Chrome over CDP against the running dev app (http://localhost:5390), 1440×900 and 390×844: screenshots closed / open / typed "arc" / picked; real mouse+key events: click field → open, Esc → closed, `/` → open, map click → closed; per-frame sampling on open: wide clip-path interpolates over ~9 frames, phone translateY 686 → 583 → 481 → 151 → 33 → 0 px; clicking the closed card's picked row → `location.search` = `?building=test%2Fosm-way50300147`.
- `uv run pytest` not run: no Python changed.
- Fix round 1: `python3 scripts/check_links.py` → `OK: all links resolve in 24 files`; `cd frontend && npx tsc -b; echo $?` → `tsc exit 0`.

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (App line)
- [x] `memory-bank/log.md` entries added (4, 2026-10-27)
- [x] decisions / open questions touched: none (UI change within D-027's brand; no new decision)
- [x] docs touched: `docs/product/visualization.md` (Landing)

## Known gaps / not done
- Not tested on a real phone (iOS keyboard with the bottom sheet) nor in real Chrome with the extension (not connected); headless only.
- `scripts/brand/steward-outline.json` and `outline.py` are no longer used by the generator; kept, not deleted.
- The logo's soft shade (`.ml-logo::before`) is barely visible; map labels can show near the logo.
- The `?view=list` page (`src/search/`) is unchanged and still has its own header ("Find a building"), no logo.
- Wordmark refinements not taken (arrival animation, rooms, live heading, floor stack) live only in a scratchpad mockup.

## Verification rounds
- Round 1: FAIL (C12 docs paragraph stale: "height animates", "closed card with Open")

## Fix round 1
- visualization.md "height animates": implemented — Landing paragraph now says the panel is always full height, cut to `--ml-top`; opening animates `clip-path` (wide) / `transform` slide up (narrow), never the height; chips and first 12 rows rise in, staggered (`docs/product/visualization.md`).
- visualization.md "closed card with Open": implemented — closed there is no card; the picked building is its own glass pill under the search pill, tapping the row opens it (**Open ›**) (`docs/product/visualization.md`).
- Optional: implemented — removed duplicate `transform 0.45s var(--ease)` from the `.ml-panel` transition list, kept `transform 0.4s var(--ease-out)`; `.ml-open .ml-panel` untouched (`frontend/src/map/map.css`). Header comment now says the search field is a pill and the card only appears once the list opens (`frontend/src/map/MapLanding.tsx`).
- Round 2: PASS (tree ed167b970ee77cab4cda85a03178b8f91de05f8c)
# Verification round 1 — VERDICT: FAIL

TREE: 843354ce8ecc177be8c713314078dd724db83c57

C1–C11 MET. C12 PARTIAL: docs/product/visualization.md Landing paragraph says "the height animates" (wrong since
clip-path/transform, C4) and "stays in the closed card with **Open**" (closed there is no card, C3/C7).
Standard checks: pytest 955 passed, 2 skipped; links OK; secrets none; score.py unchanged; no hard-coding.
Required fixes: (1) rewrite the opening-animation clause; (2) rewrite the picked-building clause; (3, optional)
drop the duplicate `transform` in the `.ml-panel` transition list; MapLanding.tsx header "a card with the search
field" → "a search pill".

# Verification round 2 — VERDICT: PASS

VERDICT: PASS
TREE: ed167b970ee77cab4cda85a03178b8f91de05f8c

C1–C12 all MET (C12: visualization.md Landing paragraph now covers pill, card, clip-path/transform "never the
height", staggered rows, "Open ›"). Standard checks: pytest 955 passed, 2 skipped (116.46 s); links OK (24 files);
secrets none; score.py unchanged; no hard-coding; working tree clean outside the staged set. Re-ran tsc (0), oxlint
(0), generator cmp (no DIFF vs staged blobs), reduced-motion count 1, `<text` count 0. Headless CDP checks not
re-run (need the dev app). Undeclared but minor: `.ml` overflow hidden, logo fade under `.ml-open`, header removed
(count moved to placeholder), `.ml-kinds` padding 10→12, `aria-expanded`/`aria-controls` and `inert` body.
