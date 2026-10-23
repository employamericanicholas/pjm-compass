"""Enrich the project table with EIA-860 annual detail (2025, falling back to 2024).

Two things the monthly 860M does not carry:

1. "Transmission or Distribution System Owner" - the utility a plant actually
   interconnects to, as *reported* by the plant. This replaces the county-inferred
   transmission zone wherever it is available, which is most of the capacity.
2. The Owner schedule - equity owners and their percentages, so a project shows its
   real owner rather than the single-purpose entity that operates it.
"""
import html
import os

import numpy as np
import pandas as pd

HUB = os.environ.get(
    "EIA_HUB", r"G:\Shared drives\EA Programs Folders\Energy + Nick\EIAHUB")
# Newest year first: a plant's 2025 filing wins, and 2024 fills in plants that did not
# file in 2025. 2025 is downloaded from EIA into data/raw; the hub only reaches 2024.
YEARS = [(2025, "data/raw/eia860_2025"), (2024, os.path.join(HUB, "EIA8602024"))]


def _sheets(name):
    """Stack one EIA-860 schedule across YEARS, tagged with its report year."""
    out = []
    for y, d in YEARS:
        f = os.path.join(d, name % y)
        if not os.path.exists(f):
            print("  missing %s - skipped" % f)
            continue
        x = pd.read_excel(f, header=1)
        x.columns = [str(c).strip() for c in x.columns]
        x["_eia860_year"] = y
        out.append(x)
    return pd.concat(out, ignore_index=True)


TD = "Transmission or Distribution System Owner"

# Reported interconnecting utility -> PJM transmission zone. These are the entities
# plants actually name, so this mapping is far firmer than a county lookup.
UTIL_ZONE = {
    "Virginia Electric & Power Co": "Dominion",
    "Commonwealth Edison Co": "ComEd",
    "Public Service Elec & Gas Co": "PSEG",
    "Jersey Central Power & Lt Co": "JCPL",
    "Baltimore Gas & Electric Co": "BGE",
    "Potomac Electric Power Co": "PEPCO",
    "PPL Electric Utilities Corp": "PPL",
    "Delmarva Power": "DPL",
    "Ohio Power Co": "AEP",
    "Pennsylvania Electric Co": "PENELEC",
    "Indiana Michigan Power Co": "AEP",
    "PECO Energy Co": "PECO",
    "Atlantic City Electric Co": "AECO",
    "Appalachian Power Co": "AEP",
    "Metropolitan Edison Co": "METED",
    "West Penn Power Company": "APS",
    "The Potomac Edison Company": "APS",
    "American Transmission Systems Inc": "ATSI",
    "Duquesne Light Co": "DLCO",
    "Monongahela Power Co": "APS",
    "East Kentucky Power Coop, Inc": "EKPC",
    "Ohio Edison Co": "ATSI",
    "Cleveland Electric Illum Co": "ATSI",
    "The Toledo Edison Co": "ATSI",
    "Pennsylvania Power Co": "ATSI",
    "Duke Energy Ohio Inc": "DEOK",
    "Duke Energy Kentucky": "DEOK",
    "Dayton Power & Light Co": "DAY",
    "AES Ohio": "DAY",
    "Old Dominion Electric Coop": "Dominion",
    "Southern Maryland Elec Coop Inc": "SMECO",
    "Rockland Electric Co": "RECO",
    "Wheeling Power Co": "AEP",
    "Kentucky Power Co": "AEP",
    "Rappahannock Electric Coop": "Dominion",
    "Northern Virginia Elec Coop": "Dominion",
    "Shenandoah Valley Elec Coop": "Dominion",
    "Central Virginia Elec Coop": "Dominion",
    "Choptank Electric Coop Inc": "DPL",
    "Delaware Electric Coop Inc": "DPL",
    "A & N Electric Coop": "DPL",
    "City of Vineland - (NJ)": "AECO",
    "City of Richmond - (IN)": "AEP",
    # post-2024 FirstEnergy consolidation: PJM still settles Met-Ed and Penelec apart,
    # so a plant reporting the merged company cannot be resolved to one of them
    "FirstEnergy Pennsylvania Electric Co": "FirstEnergy PA (Met-Ed/Penelec/Penn Power)",
    # MAIT is the FirstEnergy transco holding Met-Ed's and Penelec's transmission
    "Mid-Atlantic Interstate Transmission, LLC": "MAIT (Met-Ed/Penelec)",
    "Mid-Atlantic Interstate Transmission, LL": "MAIT (Met-Ed/Penelec)",
    # municipal and co-op systems embedded in a host zone
    "City of Anderson - (IN)": "AEP",
    "City of Auburn - (IN)": "AEP",
    "City of Sturgis": "AEP",
    "City of Wapakoneta - (OH)": "AEP",
    "City of Wadsworth - (OH)": "ATSI",
    "City of Niles - (OH)": "ATSI",
    "City of Bowling Green - (OH)": "AEP",
    "Clyde Light & Power": "ATSI",
    "City of Danville - (VA)": "Dominion",
    "Halifax Electric Member Corp": "Dominion",
    "Somerset Rural Elec Coop, Inc": "PENELEC",
    "Borough of Quakertown - (PA)": "PPL",
    "Hendricks County Rural E M C": "AEP",
    # spellings that first appear in the 2025 filings
    "AEP Ohio Transmission Company, Inc.": "AEP",
    "The Potomac Edison Co": "APS",
    "Delaware Electric Cooperative": "DPL",
    "Central Virginia Electric Coop": "Dominion",
    "Choptank Electric Cooperative, Inc": "DPL",
    "City of Cuyahoga Falls - (OH)": "ATSI",
    "West Penn Power Co": "APS",
    "Delmarva Power & Light Company": "DPL",
    # EIA's utility picklist mis-selections: an Ohio or Indiana plant naming an AEP
    # *Texas* company, or Wisconsin's American Transmission Co where FirstEnergy's
    # American Transmission Systems is meant. The plant is plainly in the PJM zone.
    "AEP Texas North Company": "AEP",
    "AEP Texas Central Company": "AEP",
    "American Transmission Co": "ATSI",
}

# Reported interconnection to a utility that is not in PJM. EIA-860M still codes these
# plants to balancing authority PJM, which cannot both be true. Surfaced, not dropped.
NON_PJM_UTILITY = {
    "Ameren Illinois Company": "MISO",
    # (First Electric Coop, an Arkansas co-op, and Duke Energy Carolinas also appear,
    # on plants deep inside PJM; those are picklist errors too and fall back to county)
    "Northern Indiana Pub Serv Co": "MISO",
    "Duke Energy Indiana, LLC": "MISO",
    "Consumers Energy Co": "MISO",
    "DTE Electric Company": "MISO",
    "Consumers Energy Co - (MI)": "MISO",
    "AES Indiana": "MISO",
}


def norm(s):
    # EIA ships some of these names HTML-escaped ("Virginia Electric &amp; Power Co")
    return html.unescape(str(s)).strip()


def main():
    src = "output/pjm_projects_online_2015_2026.csv"
    p = pd.read_csv(src)
    # Enrichment writes back into src, so a re-run would merge onto already-merged
    # columns and stack suffixed duplicates. Drop anything this script adds first.
    added = ["interconnecting_utility", "ic_utility_eia_id", "grid_voltage_kv",
             "sector_name", "regulatory_status", "zone_reported",
             "non_pjm_interconnection", "pjm_zone_final", "zone_source",
             "equity_owners", "lead_equity_owner", "lead_equity_pct"]
    p = p.drop(columns=[c for c in p.columns if c in added
                        or c.rsplit(".", 1)[0] in added and c[-2:-1] == "."],
               errors="ignore")
    p = p.loc[:, ~p.columns.str.match(r".+\.\d+$")]      # clear prior merge artifacts
    p["_pid"] = pd.to_numeric(p.eia_plant_id, errors="coerce")

    pl = _sheets("2___Plant_Y%d.xlsx")
    pl["_pid"] = pd.to_numeric(pl["Plant Code"], errors="coerce")
    keep = pl[["_pid", TD, "Transmission or Distribution System Owner ID",
               "Grid Voltage (kV)", "Sector Name", "Regulatory Status"]].drop_duplicates("_pid")
    keep = keep.rename(columns={TD: "interconnecting_utility",
                                "Transmission or Distribution System Owner ID": "ic_utility_eia_id",
                                "Grid Voltage (kV)": "grid_voltage_kv",
                                "Sector Name": "sector_name",
                                "Regulatory Status": "regulatory_status"})
    p = p.merge(keep, on="_pid", how="left")

    p["interconnecting_utility"] = p.interconnecting_utility.map(
        lambda v: norm(v) if pd.notna(v) else np.nan)
    p["zone_reported"] = p.interconnecting_utility.map(UTIL_ZONE)
    p["non_pjm_interconnection"] = p.interconnecting_utility.map(NON_PJM_UTILITY)
    bad = p[p.non_pjm_interconnection.notna()]
    if len(bad):
        print("\nEIA codes these to balancing authority PJM but the plant reports "
              "interconnecting to a non-PJM utility (%d units, %.0f MW):"
              % (len(bad), bad.capacity_added_mw.sum()))
        print(bad.groupby(["interconnecting_utility", "non_pjm_interconnection"])
                 .capacity_added_mw.agg(["size", "sum"]).round(1).to_string())

    unmapped = (p[p.interconnecting_utility.notna() & p.zone_reported.isna()]
                .groupby("interconnecting_utility").capacity_added_mw.agg(["size", "sum"])
                .sort_values("sum", ascending=False))
    if len(unmapped):
        print("interconnecting utilities with no zone mapping (%d, %.0f MW):"
              % (len(unmapped), unmapped["sum"].sum()))
        print(unmapped.head(20).round(1).to_string())

    # reported zone wins; county inference is the fallback
    p["pjm_zone_final"] = np.where(
        p.non_pjm_interconnection.notna(),
        "OUTSIDE PJM (" + p.non_pjm_interconnection.astype(str) + ")",
        np.where(p.zone_reported.notna(), p.zone_reported, p.pjm_zone))
    p["zone_source"] = np.where(
        p.non_pjm_interconnection.notna(), "reported interconnection is not a PJM utility",
        np.where(p.zone_reported.notna(), "reported to EIA-860 by the plant",
        np.where(p.pjm_zone.ne("zone unresolved"),
                 "inferred from county service territory", "unresolved")))

    # ---- equity ownership
    ow = _sheets("4___Owner_Y%d.xlsx")
    ow["_pid"] = pd.to_numeric(ow["Plant Code"], errors="coerce")
    ow["_gid"] = ow["Generator ID"].astype(str).str.strip().str.upper()
    ow["Percent Owned"] = pd.to_numeric(ow["Percent Owned"], errors="coerce")
    # keep only the newest filing year for each generator
    newest = ow.groupby(["_pid", "_gid"])["_eia860_year"].transform("max")
    ow = ow[ow._eia860_year.eq(newest)]
    p["_gid"] = p.generator_id.astype(str).str.strip().str.upper()

    def summarize(g):
        g = g.sort_values("Percent Owned", ascending=False)
        return pd.Series({
            "equity_owners": "; ".join(
                "%s (%.0f%%)" % (r["Owner Name"], 100 * r["Percent Owned"])
                for _, r in g.iterrows()),
            "lead_equity_owner": g["Owner Name"].iat[0],
            "lead_equity_pct": round(100 * g["Percent Owned"].iat[0], 1),
        })

    osum = ow.groupby(["_pid", "_gid"]).apply(summarize, include_groups=False).reset_index()
    p = p.merge(osum, on=["_pid", "_gid"], how="left")

    cov_mw = p.loc[p.interconnecting_utility.notna(), "capacity_added_mw"].sum()
    own_mw = p.loc[p.lead_equity_owner.notna(), "capacity_added_mw"].sum()
    tot = p.capacity_added_mw.sum()
    print("\ninterconnecting utility reported : %4d units, %.1f%% of MW"
          % (p.interconnecting_utility.notna().sum(), 100 * cov_mw / tot))
    print("equity ownership resolved        : %4d units, %.1f%% of MW"
          % (p.lead_equity_owner.notna().sum(), 100 * own_mw / tot))
    print("zone source (MW):")
    print(p.groupby("zone_source").capacity_added_mw.agg(["size", "sum"]).round(0).to_string())

    p.drop(columns=["_pid", "_gid"]).to_csv(src, index=False)
    print("\n-> %s (enriched in place)" % src)

    print("\nzone after using reported data (MW):")
    print(p.groupby("pjm_zone_final").capacity_added_mw.agg(["size", "sum"])
           .sort_values("sum", ascending=False).round(0).to_string())


if __name__ == "__main__":
    main()
