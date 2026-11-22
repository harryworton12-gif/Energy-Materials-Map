"""Extract world mine production and reserves for every commodity from the USGS Mineral Commodity Summaries 2025 PDF.

Run with:  python extract_usgs.py path/to/mcs2025.pdf
Download the PDF from https://pubs.usgs.gov/periodicals/mcs2025/mcs2025.pdf (public domain).

Writes, in data/:
    usgs_world.csv         one row per commodity and country: 2024 production and reserves
    usgs_commodities.csv   one row per commodity: unit, source table, world totals, and how the
                           listed countries compare with USGS's own world total (a parsing check)
    usgs_skipped.csv       chapters with no usable country table, and why

Footnote markers and the "e" (estimated) flag are printed in a smaller font than the numbers, so
they are dropped by font size instead of being glued onto the figures.
"""
import argparse
import functools
import re
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

OUT = Path(__file__).parent / "data"
NUM = re.compile(r"^[>~<]?\d[\d,]*(\.\d+)?$")
WORDS = {"—", "–", "-", "NA", "W", "XX", "Large", "Small", "Moderate"}
TABLE_START = re.compile(r"^World .*?(Production|Reserves|Capacity)[^:]*:")


def page_lines(page):
    """Rebuild the lines of a page as lists of tokens, dropping small superscripts."""
    chunks = []

    def visit(text, cm, tm, font, size):
        if not text.strip():
            return
        fs = size * (tm[0] if tm[0] else 1)
        chunks.append((round(tm[5], 1), tm[4], fs, text.strip()))

    page.extract_text(visitor_text=visit)
    chunks = [c for c in chunks if c[2] >= 8]  # footnote marks and 'e' flags are ~6.5pt
    chunks.sort(key=lambda c: (-c[0], c[1]))
    rows, cur, cur_y = [], [], None
    for c in chunks:
        if cur_y is None or abs(c[0] - cur_y) > 2:
            if cur:
                rows.append(cur)
            cur, cur_y = [], c[0]
        cur.append(c)
    if cur:
        rows.append(cur)
    lines = []
    for row in rows:
        row.sort(key=lambda c: c[1])
        toks, end = [], None
        for y, x, fs, t in row:
            t = t.replace("\ufffd", "—")
            # numbers arrive in fragments ("2,0" + "00"); words arrive whole
            if toks and re.search(r"[\d,.]$", toks[-1]) and re.match(r"^[\d,.]", t) and x - end < 0.3 * fs:
                toks[-1] += t
            else:
                toks.append(t)
            end = x + 0.52 * fs * len(t)
        lines.append(toks)
    return lines


def is_value(t):
    return bool(NUM.match(t)) or t in WORDS


def value(t):
    """Number from a USGS cell, or None if not a figure."""
    t = t.replace(",", "").lstrip(">~<")
    try:
        return float(t)
    except ValueError:
        return None


def split_row(toks):
    """('Country name', [value tokens]) for a table row."""
    first = next((k for k, t in enumerate(toks) if k > 0 and is_value(t)), None)
    if first is None:
        return " ".join(toks).strip(), []
    j = first
    while j < len(toks) and is_value(toks[j]):
        j += 1
    return " ".join(toks[:first]).strip(), toks[first:j]


def read_chapters(pdf):
    """Each commodity chapter as {name, unit, toks: [token lists, one per line]}."""
    stream = [toks for page in PdfReader(pdf).pages for toks in page_lines(page)]
    joined = [" ".join(t) for t in stream]

    starts = []
    for idx, line in enumerate(joined):
        if idx > 0 and re.match(r"^[\(\[]Data in", line):  # the unit line under each chapter title
            k = idx - 1
            while k > 0 and joined[k].startswith("("):     # skip a descriptor line between title and unit
                k -= 1
            starts.append((idx, re.sub(r"\d+$", "", joined[k].strip()), line.strip("()[] ")))
    ends = [s[0] for s in starts[1:]] + [len(stream)]
    return [{"name": name, "unit": unit, "toks": stream[start:end]}
            for (start, name, unit), end in zip(starts, ends)]


def parse_table(toks):
    """The world table of one chapter: (table title, country rows, world-total values)."""
    lines = [" ".join(t) for t in toks]
    s = next((i for i, l in enumerate(lines) if TABLE_START.match(l)), None)
    if s is None:
        return "", [], []
    title = lines[s].split(":")[0]
    pending, got = "", []
    for l, t in zip(lines[s + 1:], toks[s + 1:]):
        if l.startswith(("World Resources", "Substitutes", "eEstimated")):
            break
        name, vals = split_row(t)
        if not vals:
            # a country name wrapped onto two lines, or prose; keep short lines only
            if len(l) < 40 and not l.startswith(("Mine", "Reserves", "Capacity", "U.S. Geological", "Refinery", "Smelter")):
                pending += (" " if pending else "") + l
            continue
        if not name:
            continue
        full = f"{pending} {name}".strip() if pending and name[0].islower() else name
        pending = ""
        vs = [value(v) for v in vals]
        if full.lower().startswith("world total"):
            return title, got, vs
        got.append({"country": full, "vals": vs})
    return title, got, []


def main(pdf):
    meta = []
    for ch in read_chapters(pdf):
        title, got, world = parse_table(ch["toks"])
        meta.append({"commodity": ch["name"].title(), "unit": ch["unit"], "table": title, "n_rows": len(got),
                     "ncols": max((len(r["vals"]) for r in got), default=0), "world": world, "got": got})
    write_outputs(meta)


# ---- Stage 2: choose the right columns, convert units, match country names ---------------------
# Chapter -> [(output name, production column, reserves column or None, reserves multiplier)]. Columns count
# from 0 across the numbers in a row; the default is 0=2023, 1=2024, 2=reserves. Only chapters whose table
# has several products or an unusual layout are listed.
SPECS = {
    "Copper": [("Copper", 1, 4, 1)],
    "Bauxite And Alumina": [("Bauxite", 3, 4, 1), ("Alumina", 1, None, 1)],
    "Iron Ore": [("Iron Ore", 1, 4, 1000)],  # reserves are in million tons, production in thousand tons
    "Iron And Steel": [("Pig Iron", 1, None, 1), ("Raw Steel", 3, None, 1)],
    "Silicon": [("Ferrosilicon", 1, None, 1), ("Silicon Metal", 3, None, 1)],
    "Platinum-Group Metals": [("Palladium", 1, None, 1), ("Platinum", 3, None, 1)],
    "Potash": [("Potash", 1, 3, 1)],
    "Titanium And Titanium Dioxide": [("Titanium Sponge Metal", 1, None, 1)],
    "Clays": [("Bentonite", 1, None, 1), ("Fuller's Earth", 3, None, 1), ("Kaolin", 5, None, 1)],
    "Mica (Natural)": [("Mica (Scrap And Flake)", 1, None, 1)],
    "Aluminum": [("Aluminum", 1, None, 1)],
    "Cement": [("Cement", 1, None, 1)],
    "Magnesium Metal": [("Magnesium Metal", 1, None, 1)],  # third column is capacity
}
# some tables say in their own header that a column is in thousand tons although the chapter says tons
UNIT_FIX = {"Zirconium And Hafnium": (1000, 1000), "Molybdenum": (1, 1000), "Vanadium": (1, 1000)}
SKIP = {"Gemstones": "published as a dollar value, not a quantity", "(Fused Aluminum Oxide, Silicon Carbide, And Metallic Abrasives)": "only capacity is published",
        "Sand And Gravel (Construction)": "US only", "Stone (Crushed)": "US only", "Stone (Dimension)": "US only"}
PROSE_ONLY = "USGS gives no country-level table (text only or data not available)"

# USGS wording -> the Natural Earth names used by the map outlines
COUNTRY = {"United States": "United States of America", "Burma": "Myanmar", "Congo (Kinshasa)": "Dem. Rep. Congo",
           "Congo (Brazzaville)": "Rep. of Congo", "Korea, Republic of": "South Korea", "Korea, North": "North Korea",
           "Korea, Republic": "South Korea", "Türkiye": "Turkey", "Cote d'Ivoire": "Côte d'Ivoire", "Eswatini": "eSwatini",
           "North Macedonia": "Macedonia", "Dominican Republic": "Dominican Rep.", "Bosnia and Herzegovina": "Bosnia and Herz.",
           "Central African Republic": "Central African Rep.", "Equatorial Guinea": "Eq. Guinea", "Solomon Islands": "Solomon Is.",
           "South Sudan": "S. Sudan", "Czechia": "Czechia", "Czech Republic": "Czechia", "Western Sahara": "W. Sahara",
           "Falkland Islands": "Falkland Is.", "Laos": "Laos", "Vietnam": "Vietnam", "Russia": "Russia", "Iran": "Iran",
           "Syria": "Syria", "Slovak Republic": "Slovakia", "Timor-Leste": "Timor-Leste", "Bolivia": "Bolivia"}
UNITS = [("thousand metric tons", 1e3, "t"), ("million metric tons", 1e6, "t"), ("metric tons", 1, "t"),
         ("kilograms", 1e-3, "t"), ("thousand carats", 1e3, "carats"), ("million carats", 1e6, "carats"), ("carats", 1, "carats"),
         ("million cubic meters", 1e6, "m³"), ("thousand cubic meters", 1e3, "m³"), ("cubic meters", 1, "m³")]


def unit_of(text):
    low = text.lower()
    for label, mult, base in UNITS:
        if label in low:
            return mult, base
    return 1, "t"


def clean_country(name):
    n = re.sub(r"(?<=[a-z\)])\d+$", "", name.strip())   # stray footnote digits
    if n in COUNTRY:
        return COUNTRY[n]
    n = re.sub(r"\s*\(.*?\)", "", n)               # "Brazil (beneficiated)" -> "Brazil"
    if not n.startswith("Korea,"):
        n = n.split(",")[0]                         # "Argentina, crude ore" -> "Argentina"
    n = n.strip()
    n = COUNTRY.get(n, n)
    return known_names().get(_squash(n), n)


def _squash(s):
    return re.sub(r"[\s’'-]", "", s).lower()


@functools.cache
def known_names():
    """Country names we expect, keyed without spaces: the PDF sometimes splits a word ("Ar gentina") at a kerning gap."""
    names = set(pd.read_csv(OUT / "countries.csv").name) | set(COUNTRY.values()) | set(COUNTRY) | {"Côte d'Ivoire"}
    return {_squash(n): COUNTRY.get(n, n) for n in names}


def write_outputs(meta):
    out_rows, out_com, notes = [], [], []
    for info in meta:
        raw_name = info["commodity"]
        if info["n_rows"] == 0 or raw_name in SKIP:
            notes.append((raw_name, SKIP.get(raw_name, PROSE_ONLY if info["table"] else "no world table")))
            continue
        if "Production Capacity" in info["table"] and "Production and" not in info["table"]:
            notes.append((raw_name, "only capacity is published"))
            continue
        mult, base = unit_of(info["unit"])
        specs = SPECS.get(raw_name)
        if not specs:
            res_idx = 2 if (info["ncols"] == 3 and "Reserves" in info["table"]) else None
            specs = [(raw_name, 1, res_idx, 1)]
        pfix, rfix = UNIT_FIX.get(raw_name, (1, 1))
        for name, pi, ri, rscale in specs:
            rscale = rscale * rfix
            rows = {}
            for r in info["got"]:
                v = r["vals"]
                c = clean_country(r["country"])
                if c.lower().startswith(("other", "world", "total")) or re.fullmatch(r"\d{4}e?", c) or not c:
                    continue
                prod = v[pi] * mult * pfix if len(v) > pi and v[pi] is not None else None
                res = v[ri] * mult * rscale if ri is not None and len(v) > ri and v[ri] is not None else None
                if prod is None and res is None:
                    continue
                cur = rows.setdefault(c, {"production": None, "reserves": None})
                for k, x in (("production", prod), ("reserves", res)):
                    if x is not None:
                        cur[k] = (cur[k] or 0) + x
            w = info["world"]
            wprod = w[pi] * mult * pfix if len(w) > pi and w[pi] else None
            wres = w[ri] * mult * rscale if ri is not None and len(w) > ri and w[ri] else None
            psum = sum(x["production"] or 0 for x in rows.values())
            if wprod is None and psum:
                wprod = psum  # USGS gave no total; fall back on the sum of the countries listed
            ratio = psum / wprod if wprod else None
            out_com.append({"commodity": name, "chapter": raw_name, "unit": info["unit"], "base_unit": base,
                            "table": info["table"], "world_production": wprod, "world_reserves": wres,
                            "countries": len(rows), "listed_vs_world_total": None if ratio is None else round(ratio, 3)})
            for c, x in rows.items():
                out_rows.append({"commodity": name, "country": c, "production_2024": x["production"], "reserves": x["reserves"]})
    pd.DataFrame(out_rows).to_csv(OUT / "usgs_world.csv", index=False)
    pd.DataFrame(out_com).to_csv(OUT / "usgs_commodities.csv", index=False)
    pd.DataFrame(notes, columns=["commodity", "why_no_data"]).to_csv(OUT / "usgs_skipped.csv", index=False)
    print(f"{len(out_com)} commodities, {len(out_rows)} country rows; skipped {len(notes)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf", help="path to the Mineral Commodity Summaries PDF (e.g. mcs2025.pdf)")
    main(ap.parse_args().pdf)