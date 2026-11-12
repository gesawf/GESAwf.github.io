#!/usr/bin/env python3
"""
Build the four password-protected WF27 dashboards from the applicant-screen workbook.

    python3 tools/wf27/build.py path/to/workbook.xlsx

Input: an .xlsx download of "GESA WF 2027 — Applicant screen & shortlists"
(Google Sheets → File → Download → Microsoft Excel).

Output, for each audience (core, organisers, jury, sponsors):
    p/<slug>/index.html   the page shell (identical for all four, contains no data)
    p/<slug>/data.enc     that audience's data, AES-256-GCM encrypted with its own password

Each audience's data is trimmed BEFORE encryption, so a jury password can never
reveal contacts, revenue or internal flags: those bytes are not in the jury file.

Passwords and slugs live in a secrets file OUTSIDE the repo
(default ~/.config/gesa-wf27/secrets.json). It is created on first run with
strong random passwords. Never commit it. Re-running reuses the same slugs and
passwords, so links and passwords stay stable across data refreshes.

Requires: pip install openpyxl cryptography
"""
import argparse
import base64
import datetime as dt
import gzip
import json
import os
import re
import secrets
import shutil
import sys
from collections import Counter, OrderedDict
from pathlib import Path

try:
    import openpyxl
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:
    sys.exit("Missing dependencies. Run:  pip install openpyxl cryptography")

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
TEMPLATE = HERE / "template.html"
OUT_ROOT = REPO / "p"
DEFAULT_SECRETS = Path.home() / ".config" / "gesa-wf27" / "secrets.json"
PBKDF2_ITERATIONS = 600_000

AUDIENCES = OrderedDict([
    ("core", "Core team · Sharptext"),
    ("organisers", "Organisers · MindCET / GESA"),
    ("jury", "Jury"),
    ("sponsors", "Partners & sponsors"),
])

CRITERIA = [  # (key, sheet column header, short label)
    ("fit", "Workforce fit", "Fit"),
    ("problem", "Problem clarity & significance", "Problem"),
    ("solution", "Solution distinctiveness", "Solution"),
    ("change", "Evidence that work changed", "Change"),
    ("cred", "Evidence credibility", "Credibility"),
    ("traction", "Commercial traction", "Traction"),
    ("team", "Team capability", "Team"),
    ("scale", "Scalability", "Scale"),
    ("public", "Public value & inclusion", "Public value"),
    ("employer", "Employer readiness", "Employer"),
]

# Sponsor highlight rule: on all four shortlists (three if no MindCET v2 sheet) AND independently confirmed.
SPONSOR_WEB_CHECKS = {"Confirmed"}


# ---------------------------------------------------------------- helpers
def die(msg):
    sys.exit(f"\nERROR: {msg}\n")


def txt(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def num(v):
    if v is None or v == "" or v == "-":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^0-9.\-]", "", str(v))
    return float(s) if s not in ("", "-", ".") else None


def split_list(v, sep=","):
    return [x.strip() for x in txt(v).split(sep) if x.strip()]


def yes(v):
    return txt(v).lower() in ("yes", "true", "1")


def table(ws, header_row):
    rows = list(ws.iter_rows(values_only=True))
    hdr = [txt(h) for h in rows[header_row - 1]]
    out = []
    for i, r in enumerate(rows[header_row:], start=header_row + 1):
        if r and r[0] not in (None, ""):
            d = dict(zip(hdr, r))
            d["__row"] = i
            out.append(d)
    return hdr, out


def need(hdr, cols, sheet):
    missing = [c for c in cols if c not in hdr]
    if missing:
        die(f'Sheet "{sheet}" is missing columns: {missing}. Has the workbook layout changed?')


def counter_rows(counter, order=None, top=None):
    items = list(counter.items())
    if order:
        items.sort(key=lambda kv: order.index(kv[0]) if kv[0] in order else 999)
    else:
        items.sort(key=lambda kv: (-kv[1], kv[0]))
    if top and len(items) > top:
        rest = sum(v for _, v in items[top:])
        items = items[:top] + ([("Other (combined)", rest)] if rest else [])
    return [{"label": k, "value": v} for k, v in items]


# ---------------------------------------------------------------- read workbook
def read_workbook(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    for s in ["Read me", "Rubrics", "Scores", "Clean pipeline", "Changes vs sheet"]:
        if s not in wb.sheetnames:
            die(f'Workbook has no "{s}" tab. Download the whole spreadsheet as .xlsx.')

    # --- Rubrics: weight matrix, settings, anchors
    ws = wb["Rubrics"]
    grid = [[c for c in r] for r in ws.iter_rows(values_only=True)]
    hdr_i = next(i for i, r in enumerate(grid) if txt(r[0]) == "Rubric / lens")
    hdr = [txt(c) for c in grid[hdr_i]]
    crit_cols = [hdr.index(c[1]) for c in CRITERIA]
    rows = []
    for r in grid[hdr_i + 1:]:
        name = txt(r[0])
        if not re.match(r"^[123] ·", name):
            break
        rows.append({
            "name": name,
            "serves": txt(r[1]),
            "w": [num(r[c]) or 0.0 for c in crit_cols],
            "question": txt(r[hdr.index("Question it answers")]),
        })
    settings = {}
    anchors = {}
    for i, r in enumerate(grid):
        k = txt(r[0])
        if k.startswith("Minimum Workforce fit"):
            settings["gate"] = num(r[1])
        elif k.startswith("Shortlist length"):
            settings["length"] = int(num(r[1]))
        elif k == "Criterion" and txt(r[1]) == "What it measures":
            for rr in grid[i + 1:]:
                if not txt(rr[0]):
                    break
                anchors[txt(rr[0])] = {"measures": txt(rr[1]), "levels": [txt(x) for x in rr[2:7]]}
    if "gate" not in settings or "length" not in settings:
        die("Could not find the gate / shortlist length settings on the Rubrics tab.")

    rubrics = {
        "R1": {"name": "Shared core + lenses", "short": "Shared + lenses",
               "rows": [{"name": x["name"].split("·", 1)[1].strip(), "serves": x["serves"], "w": x["w"], "question": x["question"]}
                        for x in rows if x["name"].startswith("1 ·")]},
        "R2": {"name": "Evidence of change", "short": "Evidence of change",
               "rows": [{"name": "Evidence of change", "serves": x["serves"], "w": x["w"], "question": x["question"]}
                        for x in rows if x["name"].startswith("2 ·")]},
        "R3": {"name": "Classic", "short": "Classic",
               "rows": [{"name": "Classic", "serves": x["serves"], "w": x["w"], "question": x["question"]}
                        for x in rows if x["name"].startswith("3 ·")]},
    }
    if len(rubrics["R1"]["rows"]) != 5 or not rubrics["R2"]["rows"] or not rubrics["R3"]["rows"]:
        die("Rubric weight table did not parse as 5 + 1 + 1 rows.")
    criteria = []
    for key, col, short in CRITERIA:
        a = anchors.get(col)
        if not a:
            die(f'No 0–4 anchors found for "{col}" on the Rubrics tab.')
        criteria.append({"key": key, "label": col, "short": short, "measures": a["measures"], "levels": a["levels"]})

    # --- Scores
    ws = wb["Scores"]
    hdr, srows = table(ws, 2)
    LK = "Lists (of 4)" if "Lists (of 4)" in hdr else "Lists (of 3)"
    need(hdr, ["ID", "Company", "Country", "Region", "Late entry", "Ranked?", "R1 rank", "R2 rank", "R3 rank",
               LK, "Revenue (USD, reported)", "Funding stage", "Product stage", "Business model",
               "Website", "Reviewer note", "Web check", "Web check note", "Check source", "Data issues",
               "Israeli semifinal candidate"] + [c[1] for c in CRITERIA], "Scores")
    scored = []
    for d in srows:
        s = [num(d[c[1]]) for c in CRITERIA]
        if any(x is None for x in s):
            die(f'{d["ID"]} ({d["Company"]}) has a blank criterion score on the Scores tab.')
        scored.append({
            "id": txt(d["ID"]), "row": d["__row"], "name": txt(d["Company"]), "country": txt(d["Country"]),
            "region": txt(d["Region"]), "late": yes(d["Late entry"]), "s": s,
            "revenue": num(d["Revenue (USD, reported)"]), "funding": txt(d["Funding stage"]),
            "stage": txt(d["Product stage"]), "model": txt(d["Business model"]), "website": txt(d["Website"]),
            "note": txt(d["Reviewer note"]), "wc": txt(d["Web check"]), "wcNote": txt(d["Web check note"]),
            "wcSrc": txt(d["Check source"]), "issues": txt(d["Data issues"]),
            "il": yes(d["Israeli semifinal candidate"]),
            "conc": txt(d.get("Internal concerns (reviewer)")), "claim": txt(d.get("Claim to verify")),
            "conf": txt(d.get("Reviewer confidence")),
            "seg": txt(d.get("Prize segment")), "em": txt(d.get("Emerging market")).lower() in ("yes", "y", "true"),
            "_sheet": {"ranked": yes(d["Ranked?"]), "R1": d["R1 rank"], "R2": d["R2 rank"], "R3": d["R3 rank"],
                       "lists": int(num(d[LK]) or 0)},
        })

    # --- Clean pipeline
    ws = wb["Clean pipeline"]
    hdr, prows = table(ws, 1)
    need(hdr, ["Company", "ID", "Country", "Region", "Target market", "Main category", "Target customer",
               "Business model", "Product stage", "Track relevant", "Scored", "Revenue (USD, reported)",
               "Funding raised (USD, reported)", "Late entry", "Submitted", "Submissions merged",
               "Israeli semifinal candidate", "Website", "Contact", "Data issues", "Airtable record"], "Clean pipeline")
    pipeline = []
    for d in prows:
        sub = d["Submitted"]
        if isinstance(sub, (dt.date, dt.datetime)):
            sub = sub.strftime("%Y-%m-%d")
        pipeline.append({
            "id": txt(d["ID"]), "name": txt(d["Company"]), "country": txt(d["Country"]), "region": txt(d["Region"]),
            "tm": split_list(d["Target market"]), "cat": split_list(d["Main category"]),
            "cust": split_list(d["Target customer"]), "model": split_list(d["Business model"]),
            "stage": txt(d["Product stage"]), "track": yes(d["Track relevant"]), "scored": yes(d["Scored"]),
            "revenue": num(d["Revenue (USD, reported)"]), "fundingRaised": num(d["Funding raised (USD, reported)"]),
            "late": yes(d["Late entry"]), "submitted": txt(sub)[:10], "merged": int(num(d["Submissions merged"]) or 1),
            "il": yes(d["Israeli semifinal candidate"]), "website": txt(d["Website"]), "contact": txt(d["Contact"]),
            "issues": txt(d["Data issues"]), "rec": txt(d["Airtable record"]),
        })

    # --- Read me: key counts + prose sections
    ws = wb["Read me"]
    readme_lines, key_counts = [], []
    in_counts = False
    for r in ws.iter_rows(values_only=True):
        vals = [txt(v) for v in r if txt(v)]
        if not vals:
            continue
        if vals[0].startswith("Key counts"):
            in_counts = True
            continue
        if in_counts and len(vals) >= 2:
            key_counts.append({"label": vals[0], "value": vals[1]})
        elif not in_counts:
            readme_lines.append(vals[0])
    source_line = next((l for l in readme_lines if l.startswith("Source:")), "")

    # --- Changes vs sheet: keep as ordered sections of rows
    ws = wb["Changes vs sheet"]
    changes, cur = [], None
    for r in ws.iter_rows(values_only=True):
        vals = [txt(v) for v in r]
        while vals and not vals[-1]:
            vals.pop()
        if not vals or not any(vals):
            continue
        if len([v for v in vals if v]) == 1 and vals[0] and not vals[0].startswith("("):
            cur = {"title": vals[0], "rows": []}
            changes.append(cur)
        elif cur is not None:
            # collapse merged duplicates ("363 | 363")
            if len(vals) == 3 and vals[1] == vals[2] and vals[1] != "→":
                vals = vals[:2]
            cur["rows"].append([v for v in vals if v != "→"] if "→" in vals else vals)
    changes = [c for c in changes if c["rows"] or c["title"] != changes[0]["title"]]

    # --- Re-score vs 3 Nov (optional): previous scores and shortlist movement
    rescore = {}
    if "Re-score vs 3 Nov" in wb.sheetnames:
        _, rrows = table(wb["Re-score vs 3 Nov"], 3)
        for d in rrows:
            prev = [num(d.get(f"{c[1]} (3 Nov)")) for c in CRITERIA]
            rescore[txt(d["ID"])] = {
                "prev": [int(x) for x in prev] if all(x is not None for x in prev) else None,
                "listsOld": txt(d.get("Shortlists 3 Nov")), "listsNow": txt(d.get("Shortlists now")), "status": txt(d.get("Status")),
                "ranksOld": [txt(d.get(f"{r} rank 3 Nov")) for r in ("R1", "R2", "R3")],
                "changed": txt(d.get("Criteria that changed"))}
        rescore_title = txt(wb["Re-score vs 3 Nov"].cell(1, 1).value)
    else:
        rescore_title = ""
    # --- Applications (optional): full application text, internal only
    apps = {}
    if "Applications" in wb.sheetnames:
        _, arows = table(wb["Applications"], 3)
        for d in arows:
            apps[txt(d["ID"])] = {"sub": txt(d.get("Submitted")), "n": int(num(d.get("Submissions")) or 1),
                                  "fy": txt(d.get("Founding year")), "fs": txt(d.get("Funding stage")),
                                  "problem": txt(d.get("Problem")), "product": txt(d.get("Product")), "team": txt(d.get("Team")),
                                  "traction": txt(d.get("Traction")), "video": txt(d.get("Product video")), "deck": txt(d.get("Pitch deck"))}

    # --- MindCET v2 (optional): a separate six-criterion rubric with its own scores
    v2 = None
    if "MindCET v2" in wb.sheetnames:
        g2 = [list(r) for r in wb["MindCET v2"].iter_rows(values_only=True)]
        ic = next(i for i, r in enumerate(g2) if txt(r[0]) == "Criterion")
        iw = next(i for i, r in enumerate(g2) if txt(r[0]).startswith("Weights"))
        ih = next(i for i, r in enumerate(g2) if txt(r[0]) == "ID")
        keys = ["pain", "pedagogy", "ux", "evidence", "viability", "growth"]
        crit2 = [{"key": k, "label": txt(r[0]), "short": txt(r[1]), "desc": txt(r[2]), "levels": [txt(x) for x in r[3:7]]}
                 for k, r in zip(keys, g2[ic + 1:ic + 7])]
        hdr2 = [txt(x) for x in g2[ih]]
        srows = {}
        for r in g2[ih + 1:]:
            if not r or not txt(r[0]):
                continue
            d = dict(zip(hdr2, r))
            vals = [num(x) for x in r[2:8]]
            if any(x is None for x in vals):
                die(f'{txt(r[0])} has a blank MindCET v2 score.')
            srows[txt(r[0])] = {"v": [int(x) for x in vals], "ux": txt(d.get("UX basis")),
                                "why": txt(d.get("Reviewer reasoning (internal)")), "_rank": d.get("Rank")}
        v2 = {"criteria": crit2, "w": [num(x) or 0.0 for x in g2[iw][2:8]], "scores": srows,
              "intro": "A fourth rubric from MindCET: six criteria (pain point, pedagogy, user experience, evidence of change, "
                       "product viability, growth potential), equal weight, scored separately from the ten criteria behind the first three shortlists.",
              "note": txt(g2[1][0])}

    return {"v2": v2, "rescore": rescore, "rescoreTitle": rescore_title, "apps": apps,
            "rubrics": rubrics, "criteria": criteria, "settings": settings, "scored": scored,
            "pipeline": pipeline, "readme": readme_lines, "keyCounts": key_counts, "source": source_line,
            "changes": changes}


# ---------------------------------------------------------------- scoring (mirrors the sheet formulas)
def rubric_scores(s, rubrics):
    def dot(w):
        return sum(wi * si for wi, si in zip(w, s)) / 4
    lens = [dot(r["w"]) for r in rubrics["R1"]["rows"]]
    return {"lens": lens, "R1": sum(lens), "R2": dot(rubrics["R2"]["rows"][0]["w"]), "R3": dot(rubrics["R3"]["rows"][0]["w"])}


def compute(scored, rubrics, gate, length, v2=None):
    """Exactly the sheet's logic: key = score + change/100 + traction/1000 + (1000-row)/1e7,
    rank = 1 + count of ranked keys strictly greater."""
    ix = {c["key"]: i for i, c in enumerate(CRITERIA_KEYS)}
    res = {}
    for c in scored:
        sc = rubric_scores(c["s"], rubrics)
        ranked = c["s"][ix["fit"]] >= gate
        res[c["id"]] = {"sc": sc, "ranked": ranked, "key": {}}
        for r in ("R1", "R2", "R3"):
            res[c["id"]]["key"][r] = (sc[r] + c["s"][ix["change"]] / 100 + c["s"][ix["traction"]] / 1000
                                      + (1000 - c["row"]) / 1e7) if ranked else -1
    for r in ("R1", "R2", "R3"):
        keys = [v["key"][r] for v in res.values() if v["ranked"]]
        for v in res.values():
            v[r] = (1 + sum(1 for k in keys if k > v["key"][r])) if v["ranked"] else None
    keyv = {}
    if v2:  # MindCET v2: same gate, ties on Evidence of change then Product viability then sheet row
        for c in scored:
            d = v2["scores"].get(c["id"])
            if d and res[c["id"]]["ranked"]:
                keyv[c["id"]] = (sum(w * x for w, x in zip(v2["w"], d["v"])) / 4 + d["v"][3] / 100
                                 + d["v"][4] / 1000 + (1000 - c["row"]) / 1e7)
    for cid, v in res.items():
        v["V2"] = (1 + sum(1 for k in keyv.values() if k > keyv[cid])) if cid in keyv else None
    for v in res.values():
        v["lists"] = sum(1 for r in ("R1", "R2", "R3", "V2") if v.get(r) is not None and v[r] <= length)
    return res


CRITERIA_KEYS = [{"key": k} for k, _, _ in CRITERIA]


def self_check(wbdata):
    res = compute(wbdata["scored"], wbdata["rubrics"], wbdata["settings"]["gate"], wbdata["settings"]["length"], wbdata.get("v2"))
    bad = []
    for c in wbdata["scored"]:
        v, sh = res[c["id"]], c["_sheet"]
        if v["ranked"] != sh["ranked"]:
            bad.append(f'{c["id"]} ranked {v["ranked"]} vs sheet {sh["ranked"]}')
        for r in ("R1", "R2", "R3"):
            if (v[r] or None) != (int(sh[r]) if sh[r] not in (None, "") else None):
                bad.append(f'{c["id"]} {r} rank {v[r]} vs sheet {sh[r]}')
        if v["lists"] != sh["lists"]:
            bad.append(f'{c["id"]} lists {v["lists"]} vs sheet {sh["lists"]}')
    v2 = wbdata.get("v2")
    if v2:
        for cid, d in v2["scores"].items():
            mine = res[cid]["V2"] if cid in res else None
            sheet = int(d["_rank"]) if d["_rank"] not in (None, "") else None
            if mine != sheet:
                bad.append(f"{cid} MindCET v2 rank {mine} vs sheet {sheet}")
    if bad:
        die("Recomputed ranks differ from the sheet — the dashboard would disagree with it:\n  " + "\n  ".join(bad[:20]))
    return res


# ---------------------------------------------------------------- aggregates
STAGE_ORDER = ["Concept", "MVP", "Beta", "Released"]
FUNDING_ORDER = ["Bootstrapped", "Pre Seed", "Seed", "Early Stage - A / B round", "Late Stage - C / C+ round"]
REV_BANDS = ["No figure given", "$0", "Under $50k", "$50k–$500k", "$500k–$1M", "Over $1M"]


def implausible(p):
    return "implausible" in p["issues"].lower()


def rev_band(v):
    if v is None:
        return REV_BANDS[0]
    if v <= 0:
        return REV_BANDS[1]
    if v < 50_000:
        return REV_BANDS[2]
    if v < 500_000:
        return REV_BANDS[3]
    if v <= 1_000_000:
        return REV_BANDS[4]
    return REV_BANDS[5]


def weekly(pipeline):
    dates = sorted(dt.date.fromisoformat(p["submitted"]) for p in pipeline if p["submitted"])
    if not dates:
        return []
    start = dates[0] - dt.timedelta(days=dates[0].weekday())
    end = dates[-1]
    counts = Counter((d - start).days // 7 for d in dates)
    out, wk = [], 0
    while start + dt.timedelta(weeks=wk) <= end:
        ws_ = start + dt.timedelta(weeks=wk)
        out.append({"label": ws_.isoformat(), "value": counts.get(wk, 0)})
        wk += 1
    return out


def pipeline_charts(pipeline, include_internal):
    P = pipeline
    charts = [
        {"id": "weekly", "title": "Submissions per week", "sub": "All unique companies by submission date. The line marks the 15 Sept close.",
         "type": "weekly", "data": weekly(P), "marker": "2026-09-15"},
        {"id": "region", "title": "Region", "sub": f"{len(P)} unique companies", "type": "hbar",
         "data": counter_rows(Counter(p["region"] or "Unknown" for p in P))},
        {"id": "tm", "title": "Target market", "sub": "Companies can name more than one", "type": "hbar",
         "data": counter_rows(Counter(x for p in P for x in p["tm"]))},
        {"id": "cat", "title": "Main category", "sub": "Companies can name more than one; top 10", "type": "hbar",
         "data": counter_rows(Counter(x for p in P for x in p["cat"]), top=10)},
        {"id": "stage", "title": "Product stage", "sub": "", "type": "hbar",
         "data": counter_rows(Counter(p["stage"] or "Unknown" for p in P), order=STAGE_ORDER + ["Unknown"])},
        {"id": "model", "title": "Business model", "sub": "Companies can name more than one", "type": "hbar",
         "data": counter_rows(Counter(x for p in P for x in p["model"]))},
        {"id": "country", "title": "Top countries", "sub": f"{len(set(p['country'] for p in P))} countries in total",
         "type": "hbar", "data": counter_rows(Counter(p["country"] or "Unknown" for p in P), top=12)},
    ]
    if include_internal:
        charts.insert(5, {"id": "rev", "title": "Reported annual revenue", "sub": "As reported by applicants, not audited. Implausible values excluded.",
                          "type": "hbar", "data": counter_rows(Counter(rev_band(p["revenue"]) for p in P if not implausible(p)), order=REV_BANDS)})
        charts.append({"id": "issues", "title": "Data issues", "sub": "Flags on the clean pipeline; one company can have several",
                       "type": "hbar", "data": counter_rows(Counter(x for p in P for x in split_list(p["issues"], ";")))})
    return charts


def scored_charts(rows, title_suffix=""):
    return [
        {"id": "region", "title": "Region" + title_suffix, "sub": f"{len(rows)} companies", "type": "hbar",
         "data": counter_rows(Counter(c["region"] or "Unknown" for c in rows))},
        {"id": "stage", "title": "Product stage" + title_suffix, "sub": "", "type": "hbar",
         "data": counter_rows(Counter(c["stage"] or "Unknown" for c in rows), order=STAGE_ORDER + ["Unknown"])},
        {"id": "country", "title": "Top countries" + title_suffix, "sub": f"{len(set(c['country'] for c in rows))} countries",
         "type": "hbar", "data": counter_rows(Counter(c["country"] or "Unknown" for c in rows), top=12)},
        {"id": "wc", "title": "Web check (shortlisted only)", "sub": "Light independent check of the company and one claim", "type": "hbar",
         "data": counter_rows(Counter(c["wc"] for c in rows if c["wc"] and not c["wc"].startswith("Not checked")),
                              order=["Confirmed", "Confirmed (watch)", "Partly confirmed", "Not found"])},
    ]


# ---------------------------------------------------------------- payloads per audience
SCORED_FIELDS = {
    "core": ["id", "row", "name", "country", "region", "late", "s", "revenue", "funding", "stage", "model", "website",
             "note", "wc", "wcNote", "wcSrc", "issues", "il", "conc", "claim", "conf"],
    "organisers": ["id", "row", "name", "country", "region", "late", "s", "revenue", "funding", "stage", "model",
                   "website", "note", "wc", "wcNote", "wcSrc", "issues", "il", "conc", "claim", "conf", "seg", "em"],
    "jury": ["id", "row", "name", "country", "region", "late", "s", "stage", "website", "note", "wc", "wcNote", "wcSrc"],
}
PIPELINE_FIELDS = {
    "core": None,  # everything
    "organisers": ["id", "name", "country", "region", "tm", "cat", "cust", "model", "stage", "track", "scored",
                   "revenue", "fundingRaised", "late", "submitted", "merged", "il", "website", "issues"],
}


def pick(d, fields):
    return {k: d[k] for k in fields} if fields else {k: v for k, v in d.items() if not k.startswith("_")}


def method_block(w, audience):
    lines = w["readme"]

    def section(title, stop_titles):
        out, on = [], False
        for l in lines:
            if l == title:
                on = True
                continue
            if on and l in stop_titles:
                break
            if on:
                out.append(l)
        return out
    titles = ["How to use this workbook", "How the scores were made", "The three rubrics",
              "Light web check (shortlisted companies only)", "Before anything goes public"]
    m = {
        "how": section("How the scores were made", titles),
        "rubrics": section("The three rubrics", titles),
        "webcheck": section("Light web check (shortlisted companies only)", titles),
        "caveats": section("Before anything goes public", titles),
    }
    if audience == "sponsors":
        m["how"] = [l for l in m["how"] if "Israeli" not in l]
        m["caveats"] = ["Every figure here is as reported by the applicant; the light web check did not audit revenue or outcome numbers.",
                        "Nothing here implies GESA guarantees outcomes. Partner wording: “an opportunity to engage with an industry leader”."]
    return m


def v2_fields(w, c, internal):
    d = (w["v2"] or {}).get("scores", {}).get(c["id"]) if w.get("v2") else None
    if not d:
        return {}
    out = {"v": d["v"], "vux": d["ux"]}
    if internal:
        out["vwhy"] = d["why"]
    return out


def v2_block(w):
    v2 = w.get("v2")
    return {"criteria": v2["criteria"], "w": v2["w"], "intro": v2["intro"], "note": v2["note"]} if v2 else None


def build_payloads(w, res):
    gen = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    P, S = w["pipeline"], w["scored"]
    ranked = [c for c in S if res[c["id"]]["ranked"]]
    base_rubric = {"criteria": w["criteria"], "rubrics": w["rubrics"], "settings": w["settings"]}
    common_meta = {"generated": gen, "source": w["source"]}
    payloads = {}

    for aud in ("core", "organisers"):
        payloads[aud] = {
            "meta": {**common_meta, "audience": aud, "label": AUDIENCES[aud]},
            "features": {"reweight": True, "shortlists": True, "explorer": True, "pipeline": True, "quality": True,
                         "revenue": True, "issues": True, "il": True, "contacts": aud == "core", "csv": True,
                         "gateMin": 0, "highlights": False, "internal": True, "apptext": bool(w["apps"]),
                         **({"layout": "organisers"} if aud == "organisers" else {})},
            **base_rubric,
            "companies": [dict(pick(c, SCORED_FIELDS[aud]), prev=(w["rescore"].get(c["id"]) or {}).get("prev"), **v2_fields(w, c, True)) for c in S],
            "v2": v2_block(w),
            "apps": w["apps"],
            "rescore": [dict(v, id=k) for k, v in w["rescore"].items()
                        if v["status"] and v["status"] != "No change" and (v["status"] != "Scored for the first time" or v["listsNow"] not in ("", "0"))],
            "rescoreTitle": w["rescoreTitle"],
            "pipeline": [pick(p, PIPELINE_FIELDS[aud]) for p in P],
            "keyCounts": w["keyCounts"],
            "charts": pipeline_charts(P, True),
            "changes": w["changes"],
            "method": method_block(w, aud),
        }

    payloads["jury"] = {
        "meta": {**common_meta, "audience": "jury", "label": AUDIENCES["jury"]},
        "features": {"reweight": True, "shortlists": True, "explorer": True, "pipeline": False, "quality": False,
                     "revenue": False, "issues": False, "il": False, "contacts": False, "csv": False,
                     "gateMin": w["settings"]["gate"], "highlights": False},
        **base_rubric,
        "companies": [dict(pick(c, SCORED_FIELDS["jury"]), **v2_fields(w, c, False)) for c in ranked],
        "v2": v2_block(w),
        "keyCounts": [{"label": "Applications received (unique companies)", "value": str(len(P))},
                      {"label": "Scored for the track", "value": str(len(S))},
                      {"label": "Ranked (pass the Workforce-fit gate)", "value": str(len(ranked))}],
        "charts": scored_charts(ranked, ""),
        "method": method_block(w, "jury"),
    }

    lens_names = [r["name"] for r in w["rubrics"]["R1"]["rows"]]
    emp_i, inv_i = lens_names.index("Employer / sponsor lens"), lens_names.index("Investor lens")
    emp_max = sum(w["rubrics"]["R1"]["rows"][emp_i]["w"])
    inv_max = sum(w["rubrics"]["R1"]["rows"][inv_i]["w"])
    NLISTS = 4 if w.get("v2") else 3
    highlights = []
    for c in S:
        v = res[c["id"]]
        if v["lists"] >= NLISTS and c["wc"] in SPONSOR_WEB_CHECKS:
            highlights.append({"name": c["name"], "country": c["country"], "region": c["region"], "stage": c["stage"],
                               "website": c["website"], "note": c["note"], "wc": c["wc"],
                               "employer": round(v["sc"]["lens"][emp_i], 2), "investor": round(v["sc"]["lens"][inv_i], 2),
                               "_order": v["R1"]})
    highlights.sort(key=lambda h: h.pop("_order"))
    all3 = sum(1 for c in S if res[c["id"]]["lists"] == NLISTS)
    payloads["sponsors"] = {
        "meta": {**common_meta, "audience": "sponsors", "label": AUDIENCES["sponsors"]},
        "features": {"reweight": False, "shortlists": False, "explorer": False, "pipeline": False, "quality": False,
                     "revenue": False, "issues": False, "il": False, "contacts": False, "csv": False, "highlights": True},
        "criteria": w["criteria"],
        "rubrics": {"R1": {"name": w["rubrics"]["R1"]["name"],
                           "rows": [{"name": r["name"], "serves": r["serves"], "question": r["question"]} for r in w["rubrics"]["R1"]["rows"]]}},
        "keyCounts": [
            {"label": "Applications received", "value": str(next((k["value"] for k in w["keyCounts"] if k["label"].startswith("Records")), len(P)))},
            {"label": "Unique companies", "value": str(len(P))},
            {"label": "Countries", "value": str(len(set(p["country"] for p in P)))},
            {"label": "Workforce / lifelong-learning applicants", "value": str(sum(1 for p in P if p["track"]))},
            {"label": "Pass the workforce-fit bar", "value": str(len(ranked))},
            {"label": "On all four shortlists" if NLISTS == 4 else "On all three shortlists", "value": str(all3)},
        ],
        "charts": pipeline_charts(P, False),
        "highlights": highlights,
        "lensMax": {"employer": emp_max, "investor": inv_max},
        "method": method_block(w, "sponsors"),
    }
    return payloads


# ---------------------------------------------------------------- crypto + output
def encrypt(payload, password):
    raw = gzip.compress(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0)
    salt, iv = os.urandom(16), os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=PBKDF2_ITERATIONS).derive(password.encode("utf-8"))
    ct = AESGCM(key).encrypt(iv, raw, b"gesa-wf27-v1")
    b64 = lambda b: base64.b64encode(b).decode("ascii")
    return json.dumps({"v": 1, "kdf": "PBKDF2-SHA256", "iter": PBKDF2_ITERATIONS, "salt": b64(salt), "iv": b64(iv),
                       "aad": "gesa-wf27-v1", "ct": b64(ct)})


def gen_password():
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"  # no look-alikes (l/1, o/0, i)
    return "-".join("".join(secrets.choice(alphabet) for _ in range(5)) for _ in range(4))  # ~98 bits


def load_secrets(path):
    if path.exists():
        data = json.loads(path.read_text())
    else:
        data = {}
    changed = False
    used = {v.get("slug") for v in data.values()}
    for aud in AUDIENCES:
        if aud not in data:
            slug = secrets.token_hex(6)
            while slug in used:
                slug = secrets.token_hex(6)
            used.add(slug)
            data[aud] = {"slug": slug, "password": gen_password()}
            changed = True
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))
        os.chmod(path, 0o600)
    return data, changed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xlsx", help="Workbook downloaded from Google Sheets as .xlsx")
    ap.add_argument("--secrets", default=str(DEFAULT_SECRETS), help=f"Secrets file (default {DEFAULT_SECRETS})")
    ap.add_argument("--only", choices=list(AUDIENCES), action="append", help="Build only these audiences")
    ap.add_argument("--dump-plain", metavar="DIR", help="Also write unencrypted payloads to DIR (for checking; never commit)")
    args = ap.parse_args()

    secrets_path = Path(args.secrets).expanduser()
    try:
        secrets_path.resolve().relative_to(REPO)
        inside = True
    except ValueError:
        inside = False
    if inside:
        die("The secrets file must live outside the repository so it can never be committed.")

    w = read_workbook(args.xlsx)
    res = self_check(w)
    payloads = build_payloads(w, res)
    sec, created = load_secrets(secrets_path)
    shell = TEMPLATE.read_text(encoding="utf-8")

    OUT_ROOT.mkdir(exist_ok=True)
    known = {v["slug"] for v in sec.values()}
    for d in OUT_ROOT.iterdir():  # drop folders from retired slugs
        if d.is_dir() and d.name not in known:
            shutil.rmtree(d)
    print(f"\nWorkbook: {args.xlsx}\n{w['source']}\nRanks recomputed and match the sheet ✓\n")
    for aud in (args.only or AUDIENCES):
        out = OUT_ROOT / sec[aud]["slug"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(shell, encoding="utf-8")
        (out / "data.enc").write_text(encrypt(payloads[aud], sec[aud]["password"]), encoding="utf-8")
        if args.dump_plain:
            Path(args.dump_plain).mkdir(parents=True, exist_ok=True)
            (Path(args.dump_plain) / f"{aud}.json").write_text(json.dumps(payloads[aud], ensure_ascii=False, indent=1))
        n = len(payloads[aud].get("companies", payloads[aud].get("highlights", [])))
        print(f"  {aud:<11} /p/{sec[aud]['slug']}/   {n} companies")
    print(f"\nSecrets: {secrets_path}" + ("  (NEW — passwords generated; store them in a password manager)" if created else ""))
    print("Commit only the p/ folder changes. Never commit the workbook or the secrets file.\n")


if __name__ == "__main__":
    main()
