#!/usr/bin/env python3
"""Generate a branded 1200x630 OG image for the GESA Workforce Learning Track.

Optional tool — only needed if you change the hero copy and want the social-share
card to match. Run from the repo root:

    python3 -m venv /tmp/ogvenv && /tmp/ogvenv/bin/pip install Pillow
    /tmp/ogvenv/bin/python tools/generate-og-image.py

Writes assets/og-image.png. Edit the text/colors below to taste.
Uses macOS system fonts (Georgia/Arial) as a stand-in for Fraunces/Inter.
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1200, 630
INK = (11, 12, 14)
BODY = (238, 238, 240)
HEAD = (244, 243, 245)
MUTED = (156, 160, 166)
ACCENT = (229, 89, 52)
DIV = (58, 61, 66)
PAD = 84

SERIF = "/System/Library/Fonts/Supplemental/Georgia.ttf"
SANS_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]

def sans(size):
    for p in SANS_CANDIDATES:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()

def serif(size):
    return ImageFont.truetype(SERIF, size)

def tracked(draw, xy, text, font, fill, tracking=0):
    """Draw text with letter-spacing (tracking in px)."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        w = draw.textlength(ch, font=font)
        x += w + tracking
    return x

# --- base canvas ---
img = Image.new("RGB", (W, H), INK)

# accent radial glow, top-right (mirrors the hero gradient)
glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
gd.ellipse([W - 560, -380, W + 220, 360], fill=ACCENT + (54,))
glow = glow.filter(ImageFilter.GaussianBlur(150))
img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")

draw = ImageDraw.Draw(img)

# --- wordmark row ---
wm = serif(38)
draw.text((PAD, 64), "GESA", font=wm, fill=BODY)
wm_w = draw.textlength("GESA", font=wm)
dx = PAD + wm_w + 22
draw.line([(dx, 70), (dx, 100)], fill=DIV, width=1)
draw.text((dx + 20, 72), "Workforce Learning Track", font=sans(22), fill=MUTED)

# --- eyebrow (accent, tracked small caps) ---
tracked(draw, (PAD, 236), "A NEW PERMANENT TRACK OF THE GLOBAL EDTECH STARTUP AWARDS",
        sans(19), ACCENT, tracking=2.4)

# --- headline (serif, two lines) ---
hl = serif(86)
draw.text((PAD, 286), "Closing the skills gap", font=hl, fill=HEAD)
draw.text((PAD, 386), "won’t come from hiring.", font=hl, fill=HEAD)

# --- accent rule + footer ---
draw.line([(PAD, 520), (PAD + 200, 520)], fill=ACCENT, width=3)
draw.text((PAD, 552), "gesa.sharptext.org    ·    Finals at BETT London, January 2027",
          font=sans(23), fill=MUTED)

out = "assets/og-image.png"
img.save(out, "PNG", optimize=True)
print("wrote", out, img.size)
