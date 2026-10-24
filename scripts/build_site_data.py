"""Shape the pipeline outputs into the files the PJM Build Ledger dashboard reads.

  output/site/plants.csv    one row per plant: owner, technology, COD, MW, and measured
                            net generation (GWh) in every year since it came online
  output/site/coverage.csv  per year: months of EIA-923 data and share of online MW
                            that reported generation
  output/site/reconciliation.csv  the bridge to PJM's 23 GW, steps numbered

Ownership comes from data/manual/parent_owners.csv, researched by hand for every plant
of 20 MW or more (EIA names only the operating entity, usually a single-purpose LLC).
Smaller plants fall back to EIA's equity owner, then the EIA operator.
"""
import os
import re

import numpy as np
import pandas as pd

ROLLUP = "output/pjm_projects_rollup.csv"
UNITS = "output/pjm_projects_online_2015_2026.csv"
GEN = "output/pjm_generation_by_project_year.csv"
GEN_TECH = "output/summary_generation_by_year.csv"
OWNERS = "data/manual/parent_owners.csv"
OUT = "output/site"
SMALL_MW = 5

TECH_GROUP = {
    "Natural Gas Fired Combined Cycle": "Gas combined cycle",
    "Natural Gas Fired Combustion Turbine": "Gas & oil peaking",
    "Natural Gas Internal Combustion Engine": "Gas & oil peaking",
    "Natural Gas Steam Turbine": "Gas & oil peaking",
    "Other Natural Gas": "Gas & oil peaking",
    "Petroleum Liquids": "Gas & oil peaking",
    "Solar Photovoltaic": "Solar",
    "Onshore Wind Turbine": "Wind",
    "Offshore Wind Turbine": "Wind",
    "Batteries": "Storage",
    "Flywheels": "Storage",
}


# One name per parent, so the owner table does not split a company across spellings
# ("Invenergy" / "Invenergy Services LLC") or across its project companies ("AES Tait
# LLC"). First match wins; each plant's own wording is kept in ownership_detail.
PARENT = [
    (r"^Old Dominion", "Old Dominion Electric Cooperative"),
    (r"^Dominion", "Dominion Energy"),
    (r"Invenergy", "Invenergy"),
    (r"^AES(?![A-Za-z])", "AES"),
    (r"^AEP(?![A-Za-z])|^American Electric Power", "American Electric Power"),
    (r"^Avangrid", "Avangrid (Iberdrola)"),
    (r"^Berkshire Hathaway Energy", "Berkshire Hathaway Energy"),
    (r"^Blackstone", "Blackstone"),
    (r"^Brookfield Renewable|^Urban Grid", "Brookfield Renewable"),
    (r"^Geronimo Power", "Geronimo Power"),
    (r"^CPV(?![A-Za-z])", "CPV"),
    (r"Clearlight Energy", "Clearlight Energy (LS Power)"),
    (r"^EDF(?![A-Za-z])", "EDF power solutions"),
    (r"^EDP|^EDPRNA", "EDP Renewables"),
    (r"Energix", "Energix Renewables"),
    (r"Lightsource bp", "Lightsource bp"),
    (r"^NextEra", "NextEra Energy"),
    (r"^RWE(?![A-Za-z])", "RWE"),
    (r"^Savion \(Shell\)", "Savion (Shell)"),
    (r"^TotalEnergies", "TotalEnergies"),
    (r"^Duke Energy", "Duke Energy"),
]


def parent_name(name):
    for pat, canon in PARENT:
        if re.search(pat, str(name)):
            return canon
    return name


# EIA energy source code -> fuel, grouped as 50 States of Electricity groups them
# (landfill gas is biomass; blast-furnace and other manufactured gases are "other")
FUEL = {
    "NG": "Natural gas", "SUN": "Solar", "WND": "Wind", "WAT": "Hydro",
    "DFO": "Petroleum", "RFO": "Petroleum", "JF": "Petroleum", "KER": "Petroleum", "WO": "Petroleum",
    "LFG": "Biomass", "OBG": "Biomass", "WDS": "Biomass", "AB": "Biomass", "MSB": "Biomass", "OBS": "Biomass",
    "MWH": "Battery storage", "NUC": "Nuclear", "BIT": "Coal", "SUB": "Coal",
    "BFG": "Other gases", "OG": "Other gases",
}


def dominant(units, col, mapping, default):
    """A hybrid site takes the group of its largest component by MW."""
    t = (units.groupby(["eia_plant_id", col]).capacity_added_mw.sum()
              .reset_index().sort_values("capacity_added_mw", ascending=False)
              .drop_duplicates("eia_plant_id"))
    return t.set_index("eia_plant_id")[col].map(lambda x: mapping.get(x, default))


def main():
    os.makedirs(OUT, exist_ok=True)
    r = pd.read_csv(ROLLUP, parse_dates=["first_unit_online"])
    r["eia_plant_id"] = r.eia_plant_id.astype(int)
    u = pd.read_csv(UNITS, low_memory=False)
    g = pd.read_csv(GEN)
    last_year = int(g.year.max())

    r["tech_group"] = r.eia_plant_id.map(dominant(u, "technology", TECH_GROUP, "Other"))
    r["fuel"] = r.eia_plant_id.map(dominant(u, "energy_source", FUEL, "Other"))

    # ---- ownership: researched parent > EIA-860 lead equity owner > EIA operator
    own = pd.read_csv(OWNERS) if os.path.exists(OWNERS) else pd.DataFrame(
        columns=["eia_plant_id", "parent_owner", "ownership_detail", "confidence", "source_url"])
    own = own.drop_duplicates("eia_plant_id")
    found = own.parent_owner.notna() & own.parent_owner.astype(str).str.strip().ne("")
    own = own[found].set_index("eia_plant_id")
    r["parent_owner"] = r.eia_plant_id.map(own.parent_owner)
    r["ownership_detail"] = r.eia_plant_id.map(own.ownership_detail)
    r["owner_source_url"] = r.eia_plant_id.map(own.source_url)
    r["owner_basis"] = np.where(
        r.parent_owner.notna(), "researched (" + r.eia_plant_id.map(own.confidence).astype(str) + ")",
        np.where(r.lead_equity_owner.notna(), "EIA-860 equity owner", "EIA operator"))
    r["parent_owner"] = r.parent_owner.fillna(r.lead_equity_owner).fillna(r.owner)
    r["ownership_detail"] = r.ownership_detail.fillna(r.equity_owners).fillna(r.parent_owner)
    r["parent_owner"] = r.parent_owner.map(parent_name)

    # ---- generation, one column per calendar year
    w = g.pivot_table(index="eia_plant_id", columns="year", values="mwh", aggfunc="sum") / 1000
    w = w.reindex(columns=range(2015, last_year + 1))
    w.columns = ["gen_%d_gwh" % y for y in w.columns]
    r = r.merge(w, left_on="eia_plant_id", right_index=True, how="left")
    gcols = list(w.columns)
    r["gen_total_gwh"] = r[gcols].sum(axis=1, min_count=1)
    r["gen_reported"] = np.where(r.gen_total_gwh.notna(), "yes", "no EIA-923 record")

    # the site splits plants at 5 MW: below it is mostly community and rooftop-scale solar
    r["size_class"] = np.where(r.capacity_added_mw < SMALL_MW, "under 5 MW", "5 MW and up")
    # EIA codes these to PJM, but the plant reports a utility outside it (see enrich_eia860.py)
    flag = (u[u.non_pjm_interconnection.notna()].drop_duplicates("eia_plant_id")
              .set_index("eia_plant_id").non_pjm_interconnection)
    r["interconnection_flag"] = r.eia_plant_id.map(flag).map(
        lambda v: "reports a utility in %s, not PJM" % v if pd.notna(v) else "")

    keep = ["eia_plant_id", "plant_name", "parent_owner", "ownership_detail", "owner_basis",
            "owner_source_url", "owner", "tech_group", "fuel", "technology", "site", "size_class",
            "status", "first_unit_online", "capacity_added_mw", "net_summer_mw", "state",
            "county", "latitude", "longitude", "pjm_zone", "interconnecting_utility",
            "interconnection_flag", "capacity_factor_est", "gen_reported",
            "gen_total_gwh"] + gcols
    out = r[keep].rename(columns={"owner": "eia_operator", "capacity_added_mw": "nameplate_mw",
                                  "capacity_factor_est": "cf_2025_or_benchmark"})
    out["first_unit_online"] = out.first_unit_online.dt.strftime("%Y-%m")
    out["cod_year"] = out.first_unit_online.str.slice(0, 4).astype(int)
    for c in gcols + ["gen_total_gwh"]:
        out[c] = out[c].round(1)
    out = out.sort_values("nameplate_mw", ascending=False)
    out.to_csv(os.path.join(OUT, "plants.csv"), index=False)

    cov = pd.read_csv(GEN_TECH)[["year", "months", "pct_mw_reporting"]]
    cov.to_csv(os.path.join(OUT, "coverage.csv"), index=False)

    rec = pd.read_csv("output/reconciliation.csv")
    rec = pd.DataFrame({"step": range(1, len(rec) + 1),
                        "basis": rec.basis.str.strip().str.replace(r"^\.\.\.\s*", "", regex=True)
                                    .str.replace(r"\s*<-.*$", "", regex=True),
                        "units": rec.records, "gw": rec.GW})
    rec.to_csv(os.path.join(OUT, "reconciliation.csv"), index=False)

    print("plants %d | %.2f GW | %.0f TWh measured since 2015"
          % (len(out), out.nameplate_mw.sum() / 1000, out.gen_total_gwh.sum() / 1e3))
    print(out.groupby("owner_basis").nameplate_mw.agg(["size", "sum"]).round(0).to_string())
    print("-> %s/plants.csv, coverage.csv, reconciliation.csv" % OUT)


if __name__ == "__main__":
    main()
