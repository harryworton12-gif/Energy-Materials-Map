# Energy Minerals Atlas

An interactive world map of where the minerals behind clean energy come from: who mines them, who holds the reserves, and, for the key battery materials, who refines them and where they are shipped.

**[View the live map](https://harryworton12-gif.github.io/Energy-Materials-Map/)**

## Features

- **70 minerals** from the USGS Mineral Commodity Summaries 2025, with 2024 production and reserves for every country USGS lists.
- **Grouped by technology:** filter by batteries & EVs, solar, wind, grid, nuclear or hydrogen, and by metals, non-metals or other materials.
- **"How it's used" notes:** click a technology tag on any material to see what it does in that technology.
- **Relevance matrix:** a heatmap of which minerals matter for which technology.
- **Supply chains** for lithium, cobalt, nickel, graphite, manganese, copper, rare earths and phosphate: refining shares and trade routes drawn on the map.
- **Country profiles:** click any country to see its share of every mineral.
- **No server or install:** the whole map is a single HTML file.

## Quick start

To view the map, open the live link above, or download `index.html` and open it in any browser. It works offline.

To rebuild it from the data you need Python 3.10 or newer:

```bash
pip install -r requirements.txt
python build.py
```

## How it works

```
USGS PDF ──► extract_usgs.py ──► data/*.csv ──► build.py ──► battery-minerals-atlas.html ──► index.html
UN Comtrade ► fetch_comtrade.py ─┘   (+ hand-edited CSVs)       (page source)                 (self-contained copy)
```

1. `extract_usgs.py` reads the world production and reserves tables from the USGS PDF. It checks each table against USGS's own world total.
2. `fetch_comtrade.py` downloads trade flows from the UN Comtrade public API (about 5-10 minutes, no key needed).
3. `build.py` writes the data into the page's generated blocks (`DATA:START` and `TRADE:START`). It then makes `index.html`, a copy with the D3 libraries built in so it needs no internet connection.

The layout, styling and behaviour live in `battery-minerals-atlas.html` and are edited by hand. `build.py` never overwrites them.

### Updating the data

| To change | Edit, then run `python build.py` |
|---|---|
| Material names, symbols, type, or technology relevance scores (0-3) | `data/commodity_meta.csv` |
| The "how it's used" text | `data/energy_uses.csv` |
| Refining shares | `data/refining.csv` |
| Production and reserves for a new USGS edition | Run `python extract_usgs.py path/to/mcs.pdf` first |
| Trade routes | Run `python fetch_comtrade.py --year 2024` first |

To add a mineral, add its row to `commodity_meta.csv`, then run `extract_usgs.py` and `build.py`.

## Project structure

```
├── index.html                    self-contained page (built; served by GitHub Pages)
├── battery-minerals-atlas.html   page source: layout, styles, script and generated data blocks
├── build.py                      writes the CSV data into the page and builds index.html
├── extract_usgs.py               USGS PDF -> data/usgs_*.csv
├── fetch_comtrade.py             UN Comtrade API -> data/trade_flows.csv
├── data/
│   ├── commodity_meta.csv        names, types and technology relevance scores
│   ├── energy_uses.csv           how each mineral is used in each technology
│   ├── usgs_world.csv            production and reserves by country
│   ├── usgs_commodities.csv      world totals, units and source tables
│   ├── materials.csv             units and refining labels for the 8 battery materials
│   ├── refining.csv              refining shares by country
│   ├── home_refining.csv         countries that refine their own ore
│   ├── trade_flows.csv           trade routes (tonnes and US dollars)
│   └── countries.csv             map anchor points for trade lines
└── vendor/                       D3 and topojson-client, inlined into index.html
```

## Data sources

| Data | Source | Notes |
|---|---|---|
| Production and reserves | [USGS Mineral Commodity Summaries 2025](https://pubs.usgs.gov/publication/mcs2025) | 2024 estimates. Public domain. |
| Refining shares | [IEA Global Critical Minerals Outlook 2024](https://www.iea.org/reports/global-critical-minerals-outlook-2024) | 2023 data, rounded. Copper uses USGS 2024 refinery output. |
| Trade routes | [UN Comtrade](https://comtradeplus.un.org/) | 2024, as reported by importing countries. |
| Technology relevance and uses | Editorial | Summaries informed by IEA and US DOE critical-materials work. Judgements, not measurements. |

### Limitations

- **Missing minerals:** cesium, germanium, rubidium, scandium, thallium, thorium and yttrium are left out because USGS publishes no country figures for them.
- **Production form:** for some minerals the world total is for a product form, such as gross weight or refinery output, not mine output. The page shows the unit under each total.
- **Unshaded countries:** where USGS gives a figure only as a range, as text, or "withheld", the country is not shaded.
- **Trade data:**
  - Tonnes are product weight (ore, concentrate or intermediate), not metal content, and routes under 1% of a country's exports are hidden.
  - Some routes reflect transit rather than refining, for example DR Congo cobalt "to" Namibia and Zambia.
  - Cobalt shipped inside nickel intermediates is counted under nickel.
  - China's own graphite exports are not included.

## License

Code: [MIT](LICENSE). Data keeps its sources' terms: USGS figures are public domain, and IEA and UN Comtrade figures are used with attribution. The bundled D3 and topojson-client libraries are ISC-licensed (see [vendor/LICENSES.md](vendor/LICENSES.md)).
