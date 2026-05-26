# GESA Workforce Learning Track — site (v1)

A single-page marketing site for the GESA Workforce Learning Track. Pure HTML + Tailwind CDN + ~30 lines of vanilla JS. No build step.

## Run locally

Open `index.html` directly in a browser:

```sh
open index.html
```

Or, if you want clean asset paths and live reload, run any static server in the project root:

```sh
python3 -m http.server 8000
# then visit http://localhost:8000
```

## Deploy

Drop the folder into any static host. Tested targets:

- **GitHub Pages** — the repo is already named `Gesawf.github.io`, so pushing to `main` publishes it.
- **Netlify / Vercel / Cloudflare Pages** — point the build at this directory; no build command needed.

## File layout

```
Gesawf.github.io/
├── index.html         # the whole site
├── assets/
│   ├── favicon.svg    # 32×32 wordmark mark
│   └── og-image.png   # TODO: generate 1200×630 OG image
└── README.md
```

## TODOs before publish

Search the file for `TODO:` to find every one. The current set:

- Confirm the two unsourced market figures (`$400B+`, `63%`) against the Briefing doc.
- Replace the three sponsor-tier bullet copy blocks with the exact language from the Collateral doc.
- Confirm the curator attribution in the *Curated by* section and FAQ.
- Confirm the public-facing contact email used in the sponsor CTA and footer.
- Wire the *Apply* button (currently `#apply-placeholder`) to the live Airtable URL.
- Drop a real LinkedIn URL into the footer.
- Generate and add `assets/og-image.png` (1200×630).
- Uncomment the Plausible/Fathom analytics snippet once a domain is registered.

## Stack notes

- Tailwind via the Play CDN (`https://cdn.tailwindcss.com`). For production you can swap to a built CSS file later — not required for v1.
- Fonts: Google Fonts (`Fraunces` + `Inter`), two faces, loaded with `display=swap`.
- Animation: a single `IntersectionObserver` for fade-in reveals. Respects `prefers-reduced-motion`.
- FAQ uses native `<details>` / `<summary>` — no JS for that part.
