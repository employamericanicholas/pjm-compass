# PJM Build Ledger

Every power plant that came online in the PJM footprint from January 2015 through
September 2026, who owns it, and how much electricity it has generated in every year
since it switched on.

**Site:** https://employamericanicholas.github.io/pjm-compass/

## Headline

| | |
|---|---|
| New plants (EIA plant IDs) | **1,346**: 582 of 5 MW and up (58.9 GW), 764 under 5 MW (1.7 GW) |
| of which 20 MW and up | **289** (56.4 GW) |
| Generating units | **1,591** |
| Nameplate capacity | **60.6 GW** |
| Measured net generation, Jan 2015 – Aug 2026 | **1,663 TWh** |
| Generation in 2025 | **236 TWh** (~30% of PJM load) |

Capacity uprates of existing units are **not** counted. A new unit built at a plant
that already ran before 2015 is counted, and tagged `added at a pre-2015 plant`
(44 plants, 2.5 GW) so it can be filtered out.

PJM's public figure (~23 GW in service since 2020) is reproducible on a much narrower
basis. The cumulative walk in `output/reconciliation.csv`:

| Basis | Units | GW |
|---|---|---|
| All new units, nameplate, Jan 2015 – Sep 2026 | 1,591 | 60.60 |
| … less 2015–2019 additions (PJM counts from 2020) | 1,003 | 30.71 |
| … less units reporting a non-PJM interconnection | 957 | 30.24 |
| … less 2026 additions (through Dec 2025) | 865 | 27.54 |
| … less projects under 20 MW (queue scale) | 210 | 25.33 |
| **… on net summer capacity: PJM-comparable** | **210** | **24.46** |

## Outputs

| File | Contents |
|---|---|
| `output/site/plants.csv` | **One row per plant, start here**: owner, technology, COD, MW, GWh by year |
| `output/pjm_projects_online_2015_2026.csv` | Unit-level master table |
| `output/pjm_projects_rollup.csv` | Plant-level rollup of the unit table |
| `output/pjm_generation_by_project_year.csv` | Measured MWh by plant and year, with attribution basis |
| `output/summary_generation_by_year.csv` | TWh by year and technology, with reporting coverage |
| `output/reconciliation.csv` | The 60.6 GW → 24.5 GW bridge |
| `output/summary_by_*.csv` | Capacity by year, technology, zone and operator |
| `data/manual/parent_owners.csv` | Ownership research for every plant ≥ 20 MW, with sources |

## Sources

| Source | Used for |
|---|---|
| EIA-860M, September 2026 | Unit inventory, COD, capacity, technology, operator, location |
| EIA-860M Dec 2016–2025, Jul 2026; EIA-860 2014 | Uprate detection (measured, not counted) |
| EIA-923 via EIA API v2, Jan 2015 – Aug 2026 | Monthly net generation; 2025 capacity factors |
| EIA-860 annual 2025 (2024 fallback) | Reported interconnecting utility, equity owners |
| EIA-861 2023 Service_Territory | County → PJM zone fallback |
| Press releases, filings, trackers | Parent owner of plants ≥ 20 MW |

## Method notes, and where to distrust the numbers

**Scope.** A unit is in scope if EIA-860M places it in balancing authority `PJM` with a
first operating date from January 2015. Units that retired since are kept. Scope uses
the September 2026 BA code, so plants in OVEC (which joined PJM in December 2018) count
from their COD.

**Generation is measured, and attributed by prime mover.** EIA-923 reports by plant ×
prime mover, not by generator. Where every unit in a plant's prime-mover group came
online in 2015 or later, the group's generation is the project's, including pre-COD
test energy. Where the group also holds older units (35 plants), the new units get
their share of nameplate in each month they were online. Battery net generation is net
of charging and runs slightly negative.

**Coverage.** 94% (2015) to 99.7% of ledger capacity has EIA-923 generation in each full year. 2026
covers January–August only, and about 89% of capacity has reported so far, because small
plants file annually; 2026 will rise when EIA releases annual data. Of the 1,346 plants,
127 (mostly tiny) have no EIA-923 record.

**Ownership.** EIA names an operating entity, usually a single-purpose LLC. Plants of
20 MW or more (289 plants, 93% of capacity) were researched individually for their
current parent: 129 high confidence (a source names the owner), 119 medium (indirect
evidence, no later sale found), 41 not found. Research ran into a web-search limit
on 2015–2019 plants, so those carry more medium and not-found rows; rerunning that
research would firm them up. Smaller plants fall back to EIA's equity-owner schedule,
then to the operator. Parent names are normalized (`PARENT` in
`scripts/build_site_data.py`) so one company appears once in the owner ranking.
Ownership changes often; `researched_on` dates each row.

**Interconnection conflicts.** 47 units (0.47 GW) are coded to PJM but report an
interconnecting utility outside it, mostly community solar in Ameren Illinois (MISO)
territory. They stay in the ledger and drop out of the reconciliation. Several other
reported utilities are EIA picklist errors (an Ohio plant naming AEP *Texas*,
Wisconsin's American Transmission Co. for FirstEnergy's ATSI); those are mapped to the
PJM zone the plant obviously sits in (`UTIL_ZONE` in `scripts/enrich_eia860.py`).

**Zone caveats.** Met-Ed is under-assigned wherever county inference applies, because
its counties are shared with PPL and PECO. EIA-861 2023 is used deliberately: in 2024
FirstEnergy consolidated its Pennsylvania utilities into one filing, collapsing zones
PJM still settles separately.

## Reproducing

```bash
python -m pip install pandas openpyxl pyarrow
echo "EIA_API_KEY=<your key>" > .eia_env
# download the EIA-860M vintages named in scripts/build_uprates.py into data/raw/,
# and EIA-860 2025 (eia8602025.zip) unzipped into data/raw/eia860_2025/

PYTHONPATH=scripts python scripts/fetch_generation.py   # EIA-923 monthly, ~10 min
PYTHONPATH=scripts python scripts/build_zones.py        # county -> PJM zone fallback
PYTHONPATH=scripts python scripts/build_uprates.py      # uprates (measured, not counted)
PYTHONPATH=scripts python scripts/build_projects.py     # unit-level master table
PYTHONPATH=scripts python scripts/enrich_eia860.py      # reported utility + ownership
PYTHONPATH=scripts python scripts/rollup_projects.py    # plant-level rollup
PYTHONPATH=scripts python scripts/reconcile.py          # summaries + 23 GW bridge
PYTHONPATH=scripts python scripts/build_generation.py   # generation by plant and year
PYTHONPATH=scripts python scripts/build_site_data.py    # files the site reads
```

To refresh with a newer EIA-860M, download it and update `LATEST`, `LATEST_LABEL` and
`LATEST_Y, LATEST_M` in `scripts/eia860m.py`, and the fetch window in
`scripts/fetch_generation.py`.

The site is static: `index.html`, `assets/`, and the CSVs in `output/site/`, served
by GitHub Pages from `main`. It has two tabs, plants of 5 MW and up (`#large`) and
under 5 MW (`#small`), each with its own totals, generation chart, plant map
(Leaflet on OpenStreetMap tiles), owner ranking and plant table.
