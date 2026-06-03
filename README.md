# GESA Workforce Learning Track — site (v1)

A single-page marketing site for the GESA Workforce Learning Track. Pure HTML + Tailwind CDN + ~30 lines of vanilla JS. No build step.

Lives at **[gesawf.github.io](https://gesawf.github.io/)**.

## Run locally

Open `index.html` directly in a browser:

```sh
open index.html
```

Or, for clean relative-asset paths, run any static server in the project root:

```sh
python3 -m http.server 8000
# then visit http://localhost:8000
```

## Deploy on GitHub Pages

1. Push this directory to the `main` branch of the `GESAwf/GESAwf.github.io` repo.
2. In **Settings → Pages**, set the source to `Deploy from a branch`, branch `main`, folder `/ (root)`.
3. The site goes live at `https://gesawf.github.io/` within a few minutes.

A `.nojekyll` file is included so GitHub Pages serves files verbatim without running Jekyll.

## File layout

```
GESAwf.github.io/
├── index.html         # the whole site
├── .nojekyll          # disable Jekyll on GitHub Pages
├── assets/
│   ├── favicon.svg    # stylized G mark
│   └── og-image.png   # TODO: generate 1200×630 OG image
└── README.md
```

## TODOs before publish

Search `index.html` for `TODO:` to find every one. Current set:

- Generate `assets/og-image.png` (1200×630) for OG / Twitter card previews.
- Wire the *Apply* button (currently `#apply-placeholder`) to the live Airtable application URL.
- Confirm the public-facing contact email used in the sponsor CTA and footer (`workforce-track@globaledtechawards.org` is currently a placeholder).
- Drop a real LinkedIn URL into the footer.
- Uncomment the Plausible / Fathom analytics snippet once a domain is registered.

Source-doc-aligned (no longer TODOs):

- Sponsor-tier copy now uses verbatim language from the Collateral doc.
- Curator block resolves to *Lucian Cosinschi · LVA*.
- Prize list expanded to match the six items in the Collateral doc.
- Timeline semifinals span aligned to *Oct–Dec 2026* per the Collateral doc's "The Process" section.

## Light / dark theme

The site ships with both a dark theme (the design default) and a light theme, switchable via the toggle in the nav (sun/moon icon).

- **How it works:** every Tailwind custom color (`ink`, `body`, `muted`, `line`, `surface`, `accent`, …) points at a CSS variable. Two sets of those variables are defined — on `:root` (dark) and on `html.light` (light). Flipping the `.light` class on `<html>` re-themes the whole page; no markup changes.
- **Initial theme** is resolved by a tiny inline script in `<head>` *before paint* (so there's no flash of the wrong theme): saved choice → OS `prefers-color-scheme` → dark.
- **Choice persists** in `localStorage` under the `theme` key.
- **Accent contrast:** `#E55934` passes WCAG AA on dark but only ~3.5:1 on light, so in light mode the accent deepens to `#C5471D` (≥4.5:1 for small text) and filled-button labels flip to white. All AA-verified.
- The toggle is hidden for no-JS users (gated on the `.js` class) so nobody clicks a dead control. No-JS users get the dark default.

## Stack notes

- Tailwind via the Play CDN (`https://cdn.tailwindcss.com`). For production you can swap to a built CSS file later — not required for v1.
- Fonts: Google Fonts (`Fraunces` + `Inter`), two faces, loaded with `display=swap`.
- Animation: a single `IntersectionObserver` for fade-in reveals + a 1.5s safety-net timeout. Respects `prefers-reduced-motion`. CSS is gated on a `.js` class so the page is never trapped at opacity 0 for no-JS users.
- FAQ uses native `<details>` / `<summary>` — no JS for that part.

## Sources of truth

- **GESA Workforce Learning Track — Briefing** (Google Doc, 2026-05-06). Market sizing, comparable competitions, sponsor targets, anti-positioning notes.
- **GESAwards Workforce Learning Track — Collateral** (Google Doc). Core message, sponsor tier copy, prize language, timeline, partner outreach.

Where the two disagree, the **Collateral doc wins on phrasing**; the **Briefing wins on numbers** and on strategic positioning. (Example: the Collateral uses "world's largest EdTech startup competition" but the Briefing's anti-positioning explicitly says don't claim "largest" — so the site uses the indirect framing "8,000+ startups, 130+ countries since 2014" instead.)
