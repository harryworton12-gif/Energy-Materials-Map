"""Build the Energy Minerals Atlas page from the CSV files in data/.

Run with:  python build.py

battery-minerals-atlas.html is a single page (D3 draws the map in the browser). This script
rewrites only its two generated blocks, leaving the layout, styling and behaviour alone:

    // DATA:START ... // DATA:END     every material: production, reserves, uses, refining
    // TRADE:START ... // TRADE:END   trade routes for the eight battery materials

It then writes battery-minerals-atlas-standalone.html, the same page with its libraries
inlined so it opens without an internet connection.

Inputs (all in data/):
    usgs_world.csv, usgs_commodities.csv   from extract_usgs.py
    commodity_meta.csv, energy_uses.csv    hand-edited names, categories, relevance scores and uses
    materials.csv, refining.csv, home_refining.csv, trade_flows.csv, countries.csv
"""

import json
import math
import re
from pathlib import Path

import pandas as pd

from fetch_comtrade import QUERIES

ROOT = Path(__file__).parent
DATA = ROOT / "data"
PAGE = ROOT / "battery-minerals-atlas.html"
STANDALONE = ROOT / "battery-minerals-atlas-standalone.html"

# Libraries the page loads from the CDN; build_standalone() swaps each tag for the copy in vendor/.
LIBRARIES = {
    "d3.min.js": "https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js",
    "topojson-client.min.js": "https://cdn.jsdelivr.net/npm/topojson-client@3.1.0/dist/topojson-client.min.js",
}

MIN_ROUTE_SHARE = 0.01  # hide trade routes under 1% of a country's exports of that material

# countries.csv uses common names; the map outlines use Natural Earth names. Only the differences are listed.
NE_NAME = {
    "COD": "Dem. Rep. Congo",
    "USA": "United States of America",
    "DOM": "Dominican Rep.",
    "CAF": "Central African Rep.",
    "GNQ": "Eq. Guinea",
    "SWZ": "eSwatini",
    "SLB": "Solomon Is.",
    "BIH": "Bosnia and Herz.",
    "MKD": "Macedonia",
    "SSD": "S. Sudan",
    "ESH": "W. Sahara",
    "FLK": "Falkland Is.",
    "ATF": "Fr. S. Antarctic Lands",
}

# Energy uses, in the order of the score columns in commodity_meta.csv (and of APPS in the page).
APP_COLS = ["battery", "solar", "wind", "grid", "nuclear", "hydrogen"]
# A material's colour comes from its strongest use. Keep in step with APP_COLOR in the page's script.
APP_COLOR = {
    "battery": "#d1455f",
    "solar": "#c98a00",
    "wind": "#2f7fc1",
    "grid": "#bf6a2a",
    "nuclear": "#7d3fa8",
    "hydrogen": "#0f8a8a",
    "none": "#6b7570",
}
# The eight battery materials have hand-set colours in the page's CSS, plus refining and trade data.
ORIGINAL = {"li", "co", "ni", "c", "mn", "cu", "ree", "p"}

ATOMIC = {
    "He": 2,
    "Li": 3,
    "Be": 4,
    "B": 5,
    "C": 6,
    "Mg": 12,
    "Al": 13,
    "Si": 14,
    "P": 15,
    "S": 16,
    "K": 19,
    "Ti": 22,
    "V": 23,
    "Cr": 24,
    "Mn": 25,
    "Fe": 26,
    "Co": 27,
    "Ni": 28,
    "Cu": 29,
    "Zn": 30,
    "Ga": 31,
    "As": 33,
    "Se": 34,
    "Br": 35,
    "Sr": 38,
    "Zr": 40,
    "Nb": 41,
    "Mo": 42,
    "Pd": 46,
    "Ag": 47,
    "Cd": 48,
    "In": 49,
    "Sn": 50,
    "Sb": 51,
    "Te": 52,
    "I": 53,
    "Ta": 73,
    "W": 74,
    "Re": 75,
    "Pt": 78,
    "Au": 79,
    "Hg": 80,
    "Bi": 83,
}

# Rough tonnes per unit, used only to order the tiles by size of production.
TONNES_PER_UNIT = {"t": 1, "carats": 0.0002, "m³": 0.000179}

# What the USGS production figure measures, keyed by a word in the title of its table.
KIND = {
    "Mine": "mine production",
    "Refinery": "refinery production",
    "Smelter": "smelter production",
    "Sponge": "sponge production",
    "Alumina": "mine production",
}

# Fields every material must have; the build stops if one is missing.
REQUIRED = [
    "key",
    "sym",
    "name",
    "cat",
    "kind",
    "unit",
    "bu",
    "color",
    "apps",
    "uses",
    "prodWorld",
    "prodT",
    "resWorld",
    "prod",
    "res",
    "ref",
]


def read(name):
    return pd.read_csv(DATA / name, keep_default_na=True)


def map_names(html):
    """Country names that have an outline on the map (from the embedded TopoJSON)."""
    start = html.index("const WORLD_TOPO = ") + len("const WORLD_TOPO = ")
    topo, _ = json.JSONDecoder().raw_decode(html, start)
    return {g["properties"]["name"] for g in topo["objects"]["countries"]["geometries"]}


def country_names():
    """ISO3 code -> the name the map uses, plus the lon/lat anchor table."""
    countries = read("countries.csv").set_index("iso3")
    return {iso: NE_NAME.get(iso, name) for iso, name in countries["name"].items()}, countries


def js_unit(usgs_unit):
    """'Data in thousand metric tons, lithium content, unless...' -> 'tonnes, lithium content'."""
    u = re.sub(r"^Data in\s*", "", usgs_unit)
    u = re.sub(r",?\s*unless otherwise specified", "", u)
    u = re.sub(r"(thousand|million) metric( dry)? tons", "metric tons", u)
    u = re.sub(r"(?<=[a-z\)])\d+(?=[ ,]|$)", "", u)  # footnote digits
    return u.replace("metric tons", "tonnes").strip(" ,")


def kind_of(table):
    return next((v for k, v in KIND.items() if k in table), "production")


def replace_block(html, marker, block):
    """Swap the text between // MARKER:START and // MARKER:END for block (which includes the markers)."""
    new, n = re.subn(rf"// {marker}:START.*?// {marker}:END", lambda _: block, html, flags=re.S)
    if n != 1:
        raise SystemExit(
            f"Expected one // {marker}:START ... // {marker}:END block in {PAGE.name}, found {n}."
        )
    return new


def materials_block(outlines, name_of):
    """JS for the MATERIALS list. Returns (block, country names with no outline, number of materials)."""
    meta = read("commodity_meta.csv").fillna("")
    com = read("usgs_commodities.csv").set_index("commodity")
    world = {k: g for k, g in read("usgs_world.csv").groupby("commodity")}
    old = read("materials.csv").set_index("key")
    refining = {k: g for k, g in read("refining.csv").groupby("material")}
    uses = {}
    for u in read("energy_uses.csv").itertuples(index=False):
        uses.setdefault(u.key, {})[u.application] = u.how

    items, unmatched = [], set()
    for r in meta.itertuples(index=False):
        if r.commodity not in com.index:
            print(f"  note: {r.commodity} is in commodity_meta.csv but has no USGS table, left out")
            continue
        c = com.loc[r.commodity]
        w = world.get(r.commodity, pd.DataFrame(columns=["country", "production_2024", "reserves"]))
        prod = w[w.production_2024 > 0].set_index("country").production_2024.sort_values(ascending=False)
        res = w[w.reserves > 0].set_index("country").reserves.sort_values(ascending=False)
        unmatched |= (set(prod.index) | set(res.index)) - outlines

        scores = [int(getattr(r, a)) for a in APP_COLS]
        top = APP_COLS[scores.index(max(scores))] if max(scores) else "none"
        o = old.loc[r.key] if r.key in old.index else None
        ref = refining.get(r.key) if r.key in ORIGINAL else None
        prod_world = float(c.world_production) if pd.notna(c.world_production) else float(prod.sum())
        res_world = float(c.world_reserves) if pd.notna(c.world_reserves) else float(res.sum())

        item = {
            "key": r.key,
            "z": (
                "57–71" if r.key == "ree" else (ATOMIC.get(r.symbol) if r.category != "Other" else None)
            ),  # pure elements only
            "sym": r.symbol,
            "name": r.name,
            "cat": r.category,
            "kind": kind_of(c.table),
            "unit": o.unit if o is not None else js_unit(c.unit),
            "bu": c.base_unit,
            "role": (o.battery_role if o is not None else r.role) or "",
            "color": f"var(--{r.key})" if r.key in ORIGINAL else APP_COLOR[top],
            "apps": scores,
            "uses": uses.get(r.key, {}),
            "prodWorld": prod_world,
            "prodT": prod_world * TONNES_PER_UNIT.get(c.base_unit, 1),
            "resWorld": res_world if len(res) else 0,
            "prod": {k: float(v) for k, v in prod.items()},
            "res": {k: float(v) for k, v in res.items()},
            "ref": (
                []
                if ref is None
                else [[name_of.get(x.iso3, x.country), int(x.share_pct)] for x in ref.itertuples()]
            ),
            "refWhat": o.refining_product if o is not None else "",
            "refSrc": o.refining_source if o is not None else "",
        }
        if len(res) and pd.isna(c.world_reserves):
            item["resListedOnly"] = True
        check(item)
        items.append(item)

    items.sort(key=lambda i: (-sum(i["apps"]), i["name"]))
    body = ",\n".join(" " + json.dumps(i, ensure_ascii=False, separators=(",", ":")) for i in items)
    block = (
        "// DATA:START (generated by build.py from data/*.csv, do not edit by hand)\n"
        "const MATERIALS = [\n" + body + "\n];\n// DATA:END"
    )
    return block, unmatched, len(items)


def check(item):
    """Stop the build if a material is missing a field or has a world total the page can't divide by."""
    missing = [k for k in REQUIRED if k not in item]
    if missing:
        raise SystemExit(f"{item.get('key')}: missing {', '.join(missing)}")
    if not (item["prodWorld"] > 0 and math.isfinite(item["prodWorld"])):
        raise SystemExit(f"{item['key']}: world production is {item['prodWorld']}")
    if item["res"] and not item["resWorld"] > 0:
        raise SystemExit(f"{item['key']}: has reserves but no world reserves total")


def trade_block(name_of, countries):
    """JS for the trade routes.

    Returns (block, routes by material, country names used by routes, ISO3 codes missing from countries.csv).
    """
    trade = read("trade_flows.csv")
    trade = trade[trade.exporter_iso3 != trade.importer_iso3].copy()
    trade["share"] = trade.usd / trade.groupby(["material", "exporter_iso3"]).usd.transform("sum")
    trade = trade[trade.share >= MIN_ROUTE_SHARE]

    known = set(countries.index)
    ok = trade.exporter_iso3.isin(known) & trade.importer_iso3.isin(known)
    missing = set(trade.loc[~ok, "exporter_iso3"]) | set(trade.loc[~ok, "importer_iso3"])
    missing -= known
    trade = trade[ok]

    routes, anchors = {}, {}
    for key, grp in trade.groupby("material"):
        rows = []
        for r in grp.sort_values("usd", ascending=False).itertuples(index=False):
            a, b = name_of[r.exporter_iso3], name_of[r.importer_iso3]
            for iso, n in ((r.exporter_iso3, a), (r.importer_iso3, b)):
                anchors[n] = [float(countries.at[iso, "lon"]), float(countries.at[iso, "lat"])]
            rows.append([a, b, int(r.tonnes), int(r.usd), round(float(r.share), 4)])
        routes[key] = rows

    home = {
        k: [name_of.get(i, n) for i, n in zip(g.iso3, g.country, strict=True)]
        for k, g in read("home_refining.csv").groupby("material")
    }

    def js(obj):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

    block = (
        "// TRADE:START (generated by build.py from data/*.csv, do not edit by hand)\n"
        f"const TRADE_YEAR = {int(trade.year.max())};\n"
        f"const TRADE_PRODUCTS = {js({k: v[1] for k, v in QUERIES.items()})};\n"
        f"const TRADE = {js(routes)};  // [exporter, importer, tonnes, usd, share of exporter's exports]\n"
        f"const ANCHOR = {js(anchors)};  // name -> [lon, lat]\n"
        f"const HOME_REFINED = {js(home)};\n"
        "// TRADE:END"
    )
    used = {n for rows in routes.values() for r in rows for n in r[:2]}
    return block, routes, used, missing


def build_page():
    html = PAGE.read_text(encoding="utf-8")
    outlines = map_names(html)
    name_of, countries = country_names()

    mblock, unmatched, n_materials = materials_block(outlines, name_of)
    tblock, routes, used, missing = trade_block(name_of, countries)
    html = replace_block(html, "DATA", mblock)
    html = replace_block(html, "TRADE", tblock)
    PAGE.write_text(html, encoding="utf-8", newline="\n")

    print(
        f"Wrote {n_materials} materials and {sum(map(len, routes.values()))} trade routes "
        f"for {len(routes)} materials into {PAGE.name}."
    )
    if unmatched:
        print("  listed but not shaded (no outline on the map):", ", ".join(sorted(unmatched)))
    if used - outlines:
        print("  trade lines drawn but not clickable on the map:", ", ".join(sorted(used - outlines)))
    if missing:
        print("  skipped routes for ISO3 codes missing from countries.csv:", ", ".join(sorted(missing)))
    return html


def build_standalone(html):
    """The page with its libraries inlined and the web fonts dropped, so it opens offline."""
    for name, src in LIBRARIES.items():
        tag = f'<script src="{src}"></script>'
        if tag not in html:
            raise SystemExit(f"Expected this script tag in {PAGE.name}: {tag}")
        code = (ROOT / "vendor" / name).read_text(encoding="utf-8").replace("</script", "<\\/script")
        html = html.replace(tag, f"<script>{code}</script>")
    html = re.sub(r'<link rel="(preconnect|stylesheet)" href="https://fonts[^>]*>\n?', "", html)
    STANDALONE.write_text(html, encoding="utf-8", newline="\n")
    print(f"Wrote {STANDALONE.name} ({STANDALONE.stat().st_size // 1024} KB), no internet needed.")


if __name__ == "__main__":
    build_standalone(build_page())
