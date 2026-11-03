# GESA Workforce Learning Track — site (v1)

A single-page marketing site for the GESA Workforce Learning Track. Pure HTML + Tailwind CDN + ~30 lines of vanilla JS. No build step.

Lives at **[gesa.sharptext.org](https://gesa.sharptext.org/)** (custom domain via `CNAME`), also reachable at `gesawf.github.io`.

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
├── index.html              # the whole site
├── .nojekyll               # disable Jekyll on GitHub Pages
├── CNAME                   # custom domain (gesa.sharptext.org)
├── assets/
│   ├── favicon.svg         # stylized G mark
│   ├── og-image.png        # 1200×630 social-share card
│   └── partners/           # logo wall (aws, mynavi, geac)
├── tools/
│   └── generate-og-image.py  # optional: regenerate og-image.png
└── README.md
```

## Open items

- Drop a real LinkedIn URL into the footer (currently `#`).
- Uncomment the Plausible / Fathom analytics snippet once you want analytics (`data-domain` is already set to `gesa.sharptext.org`).
- Activate the Formspree form: the first real submission triggers a confirmation email to the form owner; click it once to start receiving enquiries.

Done: og-image generated, Apply button wired to Airtable, contact handled by the inline Formspree form (+ `gesa@sharptext.org` fallback).

Source-doc-aligned (no longer TODOs):

- Sponsor-tier copy now uses verbatim language from the Collateral doc.
- Curator block resolves to *Sharptext*.
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

- Tailwind via the Play CDN, **pinned to `3.4.17`** for reproducibility (`https://cdn.tailwindcss.com/3.4.17`). Bumping the version is a deliberate one-line edit.
- Fonts: Google Fonts (`Fraunces` + `Inter`), two faces, `display=swap`, with `preconnect` hints. Inter loads weights 400/500 only (600 was unused).
- Animation: a single `IntersectionObserver` for fade-in reveals + a 1.5s safety-net timeout. Respects `prefers-reduced-motion`. CSS is gated on a `.js` class so the page is never trapped at opacity 0 for no-JS users.
- FAQ uses native `<details>` / `<summary>` — no JS for that part.
- Structured data (`application/ld+json`), Open Graph + Twitter cards, canonical URL, and a generated `assets/og-image.png` are all in `<head>`.

## Performance & optimization

Optimizations applied while keeping the file hand-editable (no build step):

- **Images right-sized.** Logos are served near their display size; `geac.png` went from 116 KB (980 px wide) to 28 KB (360 px). All logos lazy-load with explicit `width`/`height` to prevent layout shift.
- **Fonts trimmed** to only the weights in use; `preconnect` to the font + CDN origins opens connections early.
- **Pinned Tailwind version** removes a redirect hop and makes builds reproducible.
- **`og-image.png`** is a real 1200×630 card (regenerate with `tools/generate-og-image.py` if the hero copy changes).

### The one trade-off: Tailwind runtime CDN

The Play CDN ships ~120 KB of JS that generates CSS in the browser at load time. That's the main thing a Lighthouse run will flag — but it's also **what keeps the file editable**: you can add any Tailwind class in `index.html` (or via Cowork) and it just works, no rebuild. Removing it means committing to a build step, which would break that workflow.

If you later decide raw speed matters more than zero-build editing, swap the CDN `<script>` for a prebuilt stylesheet:

```sh
npx tailwindcss@3.4.17 -i input.css -o assets/tailwind.css --minify
# then replace the <script src="…cdn.tailwindcss.com/3.4.17"></script>
# with  <link rel="stylesheet" href="assets/tailwind.css" />
```

After that, re-run the command whenever you add new utility classes. (Not done here on purpose — editability was the priority.)

## Sources of truth

- **GESA Workforce Learning Track — Briefing** (Google Doc, 2026-05-06). Market sizing, comparable competitions, sponsor targets, anti-positioning notes.
- **GESAwards Workforce Learning Track — Collateral** (Google Doc). Core message, sponsor tier copy, prize language, timeline, partner outreach.

Where the two disagree, the **Collateral doc wins on phrasing**; the **Briefing wins on numbers** and on strategic positioning. (Example: the Collateral uses "world's largest EdTech startup competition" but the Briefing's anti-positioning explicitly says don't claim "largest" — so the site uses the indirect framing "8,000+ startups, 130+ countries since 2014" instead.)

## Private WF27 dashboards (`/p/…`)

Four password-protected dashboards built from the *GESA WF 2027 — Applicant screen & shortlists* workbook, one per audience:

| Audience | What it contains |
|---|---|
| Core team (Sharptext) | Everything: all 333 companies, contacts, Airtable IDs, data issues, Israeli-semifinal flag, rubric lab, CSV export |
| Organisers (MindCET / GESA) | As core, minus contact names and Airtable record IDs |
| Jury | The 121 ranked companies: scores, ranks, reviewer notes, web check, rubric lab. No contacts, revenue, data issues or Israeli flag |
| Partners & sponsors | Pipeline statistics plus the companies on all three shortlists that the web check *Confirmed*, with employer/investor lens scores only |

**How it is protected.** This repo is public, so the data is never committed in readable form. Each audience's data is trimmed *before* encryption and written as `p/<slug>/data.enc` (AES-256-GCM, key from PBKDF2-SHA256 with 600k iterations). The browser decrypts it only after the right password is entered, so a jury password cannot open core data: those fields are not in the jury file at all. The four folders have random names, are never linked from the site or from each other, carry `noindex/noarchive/nosnippet` meta tags, have no analytics, and are disallowed for all crawlers (including AI crawlers) in `robots.txt`.

Limits worth knowing: anyone with the link *and* the password can read that audience's data, and anyone could save the encrypted file and try to guess the password offline, which is why the passwords are long and random. To revoke access, change that audience's password (below) and rebuild.

**Refresh after re-scoring:**

1. Google Sheets → File → Download → Microsoft Excel (.xlsx).
2. `pip install openpyxl cryptography` (once).
3. `python3 tools/wf27/build.py ~/Downloads/<file>.xlsx`
4. Commit the changed `p/` files and push.

The script recomputes every rank with the sheet's own formula and **stops if any rank disagrees with the sheet**, so the dashboards cannot drift from it. Links and passwords stay the same across refreshes.

**Passwords and links** are kept in `~/.config/gesa-wf27/secrets.json`, outside the repo; it is created on first run. To change a password, edit it there and rebuild. To change a link, delete that audience's entry and rebuild (a new slug and password are generated, and the old folder is removed). Never commit the workbook or the secrets file; `.gitignore` blocks `*.xlsx`, `*.csv` and `secrets*.json`.

**Who sees what** is set in `tools/wf27/build.py` (`SCORED_FIELDS`, `PIPELINE_FIELDS`, `SPONSOR_*`); the page itself is `tools/wf27/template.html`. Preview locally with `python3 -m http.server 8000` and open `http://localhost:8000/p/<slug>/`. The page has to be served over http(s) rather than opened as a file, because it fetches `data.enc`.
