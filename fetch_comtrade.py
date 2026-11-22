"""Download mine-to-refinery trade flows from UN Comtrade and save data/trade_flows.csv.

Uses the free public preview API (no key needed, rate limited, max 500 rows per call).
Flows are "mirror" data: imports reported by every country *from* each mining country,
which is more complete than the mining countries' own export reports (DR Congo, for
example, does not report to Comtrade).

Run:  python fetch_comtrade.py --year 2024
"""

import argparse
import time
from pathlib import Path

import pandas as pd
import requests

API = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
REF = "https://comtradeapi.un.org/files/v1/app/reference/Reporters.json"

# HS 6-digit codes for the ore, concentrate or intermediate that leaves the mining country.
QUERIES = {
    "li": (
        "253090,283691,282520",
        "Spodumene and other mineral concentrates (253090), lithium carbonate (283691), "
        "lithium hydroxide (282520)",
    ),
    "co": (
        "260500,810520,282200",
        "Cobalt ores (260500), cobalt mattes and hydroxide intermediates (810520), "
        "cobalt oxides and hydroxides (282200)",
    ),
    "ni": (
        "260400,750110,750120,720260",
        "Nickel ores (260400), nickel matte (750110), nickel oxide sinters and MHP (750120), "
        "ferronickel and NPI (720260)",
    ),
    "c": ("250410,250490", "Natural graphite, powder or flakes (250410) and other (250490)"),
    "mn": ("260200", "Manganese ores and concentrates (260200)"),
    "cu": ("260300,740200", "Copper ores and concentrates (260300), unrefined copper and anodes (740200)"),
    "ree": (
        "284610,284690,280530,261220",
        "Rare-earth compounds (284610, 284690), rare-earth metals (280530), monazite and similar (261220)",
    ),
    "p": ("251010,251020", "Natural calcium phosphates, unground and ground (251010, 251020)"),
}

# Comtrade partner codes of the main mining countries for each material.
MINERS = {
    "li": [36, 152, 716, 32, 76, 124, 516, 620],
    "co": [180, 360, 643, 36, 608, 192, 450, 598, 792, 124],
    "ni": [360, 608, 643, 124, 36, 540, 76, 842],
    "c": [450, 508, 76, 834, 699, 643, 124, 410, 579, 144],
    "mn": [710, 266, 36, 288, 699, 76, 458, 384],
    "cu": [152, 180, 604, 360, 842, 643, 36, 398, 484, 894, 124, 616],
    "ree": [104, 842, 36, 566, 764, 450, 699, 643, 704],
    "p": [504, 842, 643, 400, 682, 76, 818, 604, 788, 704],
}


def get(url, params=None, tries=6):
    for i in range(tries):
        r = requests.get(url, params=params, timeout=60)
        if r.status_code == 429:  # rate limited: back off and retry
            time.sleep(3 + 2 * i)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"Comtrade kept rate-limiting {params}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "data" / "trade_flows.csv")
    args = ap.parse_args()

    ref = get(REF)["results"]
    iso3 = {r["reporterCode"]: r["reporterCodeIsoAlpha3"] for r in ref}
    name = {r["reporterCode"]: r["reporterDesc"] for r in ref}

    rows = []
    for mat, (cmd, _) in QUERIES.items():
        for partner in MINERS[mat]:
            j = get(API, {"period": args.year, "partnerCode": partner, "cmdCode": cmd, "flowCode": "M"})
            for d in j.get("data", []):
                if (
                    d["reporterCode"] == 0
                    or d["partner2Code"] != 0
                    or d["motCode"] != 0
                    or d["customsCode"] != "C00"
                ):
                    continue
                rows.append(
                    {
                        "material": mat,
                        "year": args.year,
                        "hs": d["cmdCode"],
                        "exporter_iso3": iso3.get(partner),
                        "exporter": name.get(partner, partner),
                        "importer_iso3": iso3.get(d["reporterCode"]),
                        "importer": name.get(d["reporterCode"], d["reporterCode"]),
                        "tonnes": (d.get("netWgt") or 0) / 1000,
                        "usd": d.get("primaryValue") or 0,
                    }
                )
            print(f"{mat} from {name.get(partner, partner)}: done")
            time.sleep(1.5)

    if not rows:
        raise SystemExit(f"Comtrade returned no flows for {args.year}; {args.out} left unchanged.")
    df = pd.DataFrame(rows)
    df = df.groupby(
        ["material", "year", "exporter_iso3", "exporter", "importer_iso3", "importer"], as_index=False
    )[["tonnes", "usd"]].sum()
    df.to_csv(args.out, index=False)
    print(f"Saved {len(df)} routes to {args.out}")


if __name__ == "__main__":
    main()
