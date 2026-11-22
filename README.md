# Energy Minerals Atlas

An interactive world map of where minerals that matter for the energy transition are produced, how much each country holds in reserves, and (for the eight battery materials) who refines them and where they are traded. It covers 70 materials from the USGS Mineral Commodity Summaries 2025, grouped by the technologies that use them: batteries, solar, wind, grid, nuclear and hydrogen. A heatmap at the bottom shows which materials matter for which technology.

## Open it

Open `battery-minerals-atlas.html` in a browser. No server is needed, but it loads its charting library and fonts from the internet.

`battery-minerals-atlas-standalone.html` is the same page with the libraries built in, so it opens offline and is the one to email or host.

## Rebuild it from the data

Python keeps the page in step with the CSV files in `data/`. You need Python 3.10 or newer and `pip install -r requirements.txt`.

```bash
# only when USGS publishes a new edition (download the PDF from pubs.usgs.gov/periodicals/mcs2025/mcs2025.pdf)
python extract_usgs.py path/to/mcs2025.pdf   # writes data/usgs_world.csv and usgs_commodities.csv

# optional: refresh the trade routes from UN Comtrade (about 5-10 minutes, no key needed)
python fetch_comtrade.py --year 2024

# copy all the data into the page and rebuild the standalone copy
python build.py
```

The Python code is formatted with [black](https://black.readthedocs.io) and checked with [ruff](https://docs.astral.sh/ruff/); both read their settings from `pyproject.toml`.

`build.py` replaces only the generated blocks in the HTML (marked `DATA:START` and `TRADE:START`). Layout, styling, behaviour and the text at the bottom of the page are edited by hand in `battery-minerals-atlas.html` and are never overwritten.

## Files

| File | What it holds |
|---|---|
| `battery-minerals-atlas.html` | The page: layout, styling and behaviour, plus the generated data blocks |
| `battery-minerals-atlas-standalone.html` | Built by `build.py`: the same page with its libraries inlined, for offline use and sharing |
| `build.py` | Copies the CSV data into the page |
| `extract_usgs.py` | Reads the USGS PDF tables into CSV files and checks each table against USGS's own world total |
| `fetch_comtrade.py` | Downloads trade routes from UN Comtrade (`build.py` also reads its product list) |
| `vendor/` | The d3 and topojson libraries used for the standalone copy |
| `data/commodity_meta.csv` | Each material's name, symbol, type (metal, non-metal or other) and its 0-3 relevance score for each technology |
| `data/energy_uses.csv` | The text explaining how each material is used in each technology |
| `data/usgs_world.csv` | Production and reserves by country, in tonnes unless the material uses another unit |
| `data/usgs_commodities.csv` | World totals, units and the USGS table each material came from |
| `data/materials.csv`, `refining.csv`, `home_refining.csv` | Names, refining shares and home-refining countries for the eight battery materials |
| `data/trade_flows.csv` | Trade routes for the eight battery materials: tonnes and US dollars |
| `data/countries.csv` | A map anchor point (latitude, longitude) for each country |

The relevance scores and the "how it's used" text are editorial summaries, not USGS data. Edit the CSV and rerun `python build.py`.

## Sources and caveats

- **Production and reserves:** USGS Mineral Commodity Summaries 2025. Production is the 2024 estimate. For some minerals the world total is for a product form (gross weight, or refinery rather than mine output), so check the unit under the world total on the page. Where USGS gives only a range, text or "withheld", the country is not shaded.
- **Not covered:** cesium, germanium, rubidium, scandium, thallium, thorium and yttrium, and a few bulk materials, because USGS publishes no country figures for them.
- **Refining shares:** IEA Global Critical Minerals Outlook 2024 (2023 data), rounded. Copper uses USGS 2024 refinery output.
- **Trade routes:** UN Comtrade 2024, as reported by importing countries ("mirror" data), because several mining countries such as DR Congo don't report their own exports. Tonnes are product weight (ore, concentrate or intermediate), not metal content. Routes under 1% of a country's exports are hidden.
- Some routes reflect transit or customs reporting rather than refining, for example DR Congo cobalt "to" Namibia and Zambia (export corridors). Cobalt that leaves Indonesia, Cuba, Papua New Guinea and the Philippines inside nickel intermediates is counted under nickel. China's own graphite exports are not included.

## License

The code is released under the [MIT License](LICENSE). The data keeps its sources' terms: USGS figures are public domain, IEA refining shares and UN Comtrade trade data are used with attribution under their providers' terms. The bundled D3 and topojson-client libraries are ISC-licensed (see [vendor/LICENSES.md](vendor/LICENSES.md)).
