"""Build the master list of new PJM generating units that reached commercial operation
2015-2026. Uprates of existing units are deliberately out of scope; build_uprates.py
still measures them, but they are not counted here.

Sources
  EIA-860M (Sep 2026 + Dec 2016-2025 vintages; EIA-860 2014 baseline) : unit inventory, COD, capacity, location, owner
  EIA-923 via EIA API v2                       : monthly net generation -> capacity factors
  EIA-861 (2023)                               : service territory -> PJM zone + footprint check
"""
import calendar
import difflib
import re

import numpy as np
import pandas as pd

from eia860m import LATEST, LATEST_M, LATEST_Y, load

START_Y = 2015
CUTOFF_Y, CUTOFF_M = LATEST_Y, LATEST_M
CF_YEAR = 2025                        # reference year for measured capacity factors

PJM_STATES = {"PA", "NJ", "MD", "DE", "VA", "WV", "OH", "IN", "IL", "MI", "KY", "NC", "TN", "DC"}

# storage and fossil peakers are dispatched, not resource-limited; a "capacity factor"
# for a battery computed from EIA net generation is negative by construction
STORAGE_TECH = {"Batteries", "Flywheels", "Hydroelectric Pumped Storage"}

SOLAR_BANDS = [(0, 5, "<5 MW"), (5, 20, "5-20 MW"), (20, 100, "20-100 MW"), (100, 1e9, ">100 MW")]

# A combined-cycle block reports generation split across its combustion-turbine (CT),
# steam (CA) and single-shaft (CS) prime movers, but nameplate is booked to those codes
# on a different basis. Dividing them yields nonsense (CTs over 80%, steam tails near
# zero), so the whole block is treated as one unit for capacity-factor purposes.
CC_PRIME_MOVERS = {"CT", "CA", "CS"}

# Minimum full-year capacity factor that a working plant of this type can physically
# post. Values below these indicate an EIA-923 reporting gap, not a bad plant, so they
# are excluded when building peer benchmarks. Dispatchable fossil is deliberately
# absent: a peaker running 0.5% of the year is doing exactly its job.
PLAUSIBILITY_FLOOR = {
    "Solar Photovoltaic": 0.06,
    "Onshore Wind Turbine": 0.10,
    "Offshore Wind Turbine": 0.10,
}

# The other tail: no PJM-latitude solar plant posts a 46% annual capacity factor, and
# one in the data does. That is a nameplate/generation mismatch in the source, not a
# record-setting plant, so such values are refused as measurements and benchmarked.
PLAUSIBILITY_CEIL = {
    "Solar Photovoltaic": 0.32,
    "Onshore Wind Turbine": 0.55,
    "Offshore Wind Turbine": 0.60,
}


def pm_group(pm):
    return "CC" if str(pm).strip().upper() in CC_PRIME_MOVERS else str(pm).strip().upper()


def month_hours(y, m):
    return calendar.monthrange(y, m)[1] * 24


def norm_county(c):
    c = str(c).strip().lower()
    c = re.sub(r"\b(county|parish|census area|municipality|city and borough|borough)\b", " ", c)
    c = re.sub(r"\bcity\b", " ", c)
    c = re.sub(r"\bst\.?\b", "saint", c)
    return re.sub(r"[^a-z]", "", c)


def band(mw):
    for lo, hi, lab in SOLAR_BANDS:
        if lo <= mw < hi:
            return lab
    return "unknown"


# ---------------------------------------------------------------- new build records
def new_builds():
    op = load(LATEST, "Operating")
    rt = load(LATEST, "Retired")
    op["_status_grp"] = np.where(
        op["Status"].astype(str).str.contains("SB", na=False), "standby", "operating")
    rt["_status_grp"] = "retired since COD"
    d = pd.concat([op, rt], ignore_index=True)
    d = d[(d["Balancing Authority Code"] == "PJM") &
          (d["Operating Year"] >= START_Y) &
          (d["Operating Year"] <= CUTOFF_Y)].copy()
    d = d[~((d["Operating Year"] == CUTOFF_Y) & (d["Operating Month"] > CUTOFF_M))]
    d["record_type"] = "new build"
    d["delta_mw"] = d["Nameplate Capacity (MW)"]
    # A new unit at a site that already generated before 2015 (a peaker added at an
    # old coal station) is new steel but not a new plant; flag it so it can be split out.
    every = pd.concat([op, rt], ignore_index=True)
    first = every.groupby("Plant ID")["Operating Year"].min()
    d["site"] = np.where(d["Plant ID"].map(first) < START_Y,
                         "added at a pre-%d plant" % START_Y, "new plant")
    return d


# ---------------------------------------------------------------- capacity factors
def measured_cf():
    """CF by plant x prime mover for the reference year, from EIA-923 net generation."""
    raw = pd.read_csv("data/interim/gen_monthly.csv.gz")
    g = raw[(raw.fuel2002 == "ALL") & (raw.primeMover != "ALL")].copy()
    if g.empty:   # this dataset carries no (ALL fuel, specific prime mover) rollup
        g = raw[(raw.fuel2002 != "ALL") & (raw.primeMover != "ALL")].copy()
        g = g.groupby(["plantCode", "primeMover", "period"], as_index=False)["generation"].sum()
    g["year"] = g.period.str.slice(0, 4).astype(int)
    g = g[g.year == CF_YEAR]
    g["pmg"] = g.primeMover.map(pm_group)
    gen = (g.groupby(["plantCode", "pmg"], as_index=False)
             .agg(mwh=("generation", "sum"), months=("period", "nunique")))

    inv = load("data/raw/eia860m_dec2025.xlsx", "Operating")
    inv = inv[inv["Balancing Authority Code"] == "PJM"].copy()
    online = inv[(inv["Operating Year"] < CF_YEAR) |
                 ((inv["Operating Year"] == CF_YEAR) & (inv["Operating Month"] <= 1))].copy()
    online["pmg"] = online["Prime Mover Code"].map(pm_group)
    cap = (online.groupby(["Plant ID", "pmg"], as_index=False)
                 .agg(cap_mw=("Nameplate Capacity (MW)", "sum"),
                      Technology=("Technology", "first")))
    # A plant that grew mid-year would get a full year of generation over a partial
    # year of capacity, inflating its CF (one Virginia solar plant came out at 46.6%,
    # which is physically impossible). Keep only plants whose rating held steady
    # across the reference year.
    prior = load("data/raw/eia860m_dec2024.xlsx", "Operating")
    prior = prior[prior["Balancing Authority Code"] == "PJM"].copy()
    prior["pmg"] = prior["Prime Mover Code"].map(pm_group)
    cap_prior = (prior.groupby(["Plant ID", "pmg"], as_index=False)
                      .agg(cap_prior=("Nameplate Capacity (MW)", "sum")))
    cap = cap.merge(cap_prior, on=["Plant ID", "pmg"], how="left")
    steady = cap.cap_prior.notna() & np.isclose(cap.cap_mw, cap.cap_prior, rtol=0.02)
    print("  CF sample: %d of %d plant/prime-mover groups held a steady rating through %d"
          % (int(steady.sum()), len(cap), CF_YEAR))
    cap = cap[steady]

    m = gen.merge(cap, left_on=["plantCode", "pmg"],
                  right_on=["Plant ID", "pmg"], how="inner")
    hours = sum(month_hours(CF_YEAR, mo) for mo in range(1, 13))
    m = m[(m.cap_mw > 0) & (m.months == 12)].copy()
    m["cf"] = m.mwh / (m.cap_mw * hours)
    m = m[(m.cf >= 0) & (m.cf <= 1.05)]
    m["state"] = m["Plant ID"].map(online.drop_duplicates("Plant ID")
                                        .set_index("Plant ID")["Plant State"])
    m["band"] = m.cap_mw.map(band)

    # A resource-limited plant cannot physically sit near zero for a full year: EIA-923
    # carries small plants that under-report or report no generation at all, and those
    # zeros drag the small-project benchmarks to absurd levels (NJ solar at 3.8%).
    # Drop them from the *benchmark* sample only; a plant's own measured value stands.
    m["plausible"] = True
    for tech, floor in PLAUSIBILITY_FLOOR.items():
        bad = m.Technology.eq(tech) & m.cf.lt(floor)
        if bad.any():
            print("  CF sample: refused %3d %s plants below %.0f%% "
                  "(under-reporting, not performance)" % (bad.sum(), tech, floor * 100))
        m.loc[bad, "plausible"] = False
    for tech, ceil in PLAUSIBILITY_CEIL.items():
        bad = m.Technology.eq(tech) & m.cf.gt(ceil)
        if bad.any():
            print("  CF sample: refused %3d %s plants above %.0f%% "
                  "(source nameplate/generation mismatch)" % (bad.sum(), tech, ceil * 100))
        m.loc[bad, "plausible"] = False
    return m


MIN_SAMPLE = 3   # a median over one or two plants is an anecdote, not a benchmark


def _median_table(frame, keys):
    """Median CF by group, suppressing groups too small to mean anything.

    Without this, a single 0.3 MW Illinois plant running at 8% became the benchmark
    for 208 other projects.
    """
    g = frame.groupby(keys)["cf"].agg(["size", "median"])
    g = g[g["size"] >= MIN_SAMPLE]
    return g["median"].to_dict()


def attach_cf(df, m):
    b = m[m.plausible]
    exact = b.set_index(["plantCode", "pmg"])["cf"].to_dict()
    solar = b[b.Technology == "Solar Photovoltaic"]
    by_tech_state = _median_table(b, ["Technology", "state"])
    by_tech = b.groupby("Technology")["cf"].median().to_dict()   # last resort, any n
    by_solar_band = _median_table(solar, "band")
    by_solar_state_band = _median_table(solar, ["state", "band"])

    full_year = ((df["Operating Year"] < CF_YEAR) |
                 ((df["Operating Year"] == CF_YEAR) & (df["Operating Month"] <= 1)))
    cfs, methods = [], []
    for pid, pm, tch, stt, mw, fy in zip(df["Plant ID"], df["Prime Mover Code"],
                                         df["Technology"], df["Plant State"],
                                         df["delta_mw"], full_year):
        if tch in STORAGE_TECH:
            cfs.append(np.nan)
            methods.append("n/a - storage (EIA net generation is net of charging)")
            continue
        v = exact.get((pid, pm_group(pm)))
        if v is not None and fy:
            cfs.append(round(v, 4)); methods.append("measured %d, this plant" % CF_YEAR); continue
        b = band(mw if pd.notna(mw) else 0)
        tail = "" if fy else "; unit not online for full %d" % CF_YEAR
        if tch == "Solar Photovoltaic":
            v = by_solar_state_band.get((stt, b))
            if v is not None and np.isfinite(v):
                cfs.append(round(float(v), 4))
                methods.append("benchmark: %s solar, %s%s" % (stt, b, tail)); continue
            v = by_solar_band.get(b)
            if v is not None and np.isfinite(v):
                cfs.append(round(float(v), 4))
                methods.append("benchmark: PJM solar, %s%s" % (b, tail)); continue
        v = by_tech_state.get((tch, stt))
        if v is not None and np.isfinite(v):
            cfs.append(round(float(v), 4))
            methods.append("benchmark: %s %s%s" % (stt, tch, tail)); continue
        v = by_tech.get(tch)
        if v is not None and np.isfinite(v):
            cfs.append(round(float(v), 4))
            methods.append("benchmark: PJM %s%s" % (tch, tail)); continue
        cfs.append(np.nan); methods.append("no basis")
    df["capacity_factor_est"] = cfs
    df["cf_method"] = methods
    return df


# ---------------------------------------------------------------- zone / footprint
def add_zone(df):
    """Attach PJM transmission zone by county.

    Caveat worth stating plainly: this maps counties by *retail* service territory,
    but a generator interconnects to *transmission*. A transmission owner's lines
    routinely cross counties where it serves no retail load, so a plant can sit in
    PJM (EIA's balancing-authority code is the authority on that) while no PJM
    utility serves that county at retail. Those get "zone unresolved", not excluded.
    """
    z = pd.read_csv("data/interim/county_to_zone.csv")
    z = z[z.state.isin(PJM_STATES)]
    df["_ck"] = df["County"].map(norm_county)
    df["_st"] = df["Plant State"].astype(str).str.strip().str.upper()

    # repair county spellings that do not match EIA-861 (e.g. "Prince Geroges")
    valid = z.groupby("state")["county_key"].apply(lambda s: sorted(set(s))).to_dict()
    fixed = {}
    for st, ck in set(zip(df["_st"], df["_ck"])):
        if st in valid and ck not in valid[st]:
            hit = difflib.get_close_matches(ck, valid[st], n=1, cutoff=0.86)
            if hit:
                fixed[(st, ck)] = hit[0]
    if fixed:
        print("county spellings repaired by fuzzy match: %d" % len(fixed))
        for (st, ck), v in sorted(fixed.items())[:12]:
            print("   %s %-18s -> %s" % (st, ck, v))
    df["_ck"] = [fixed.get((s, c), c) for s, c in zip(df["_st"], df["_ck"])]

    out = df.merge(z[["state", "county_key", "pjm_zone", "zone_alts",
                      "zone_confidence", "in_pjm_footprint"]],
                   left_on=["_st", "_ck"], right_on=["state", "county_key"], how="left")

    zoned = out.pjm_zone.notna() & out.pjm_zone.ne("zone undetermined")
    in_pjm_state = out["_st"].isin(PJM_STATES)
    out["pjm_zone"] = np.where(zoned, out.pjm_zone, "zone unresolved")
    out["zone_basis"] = np.where(
        zoned, "county in PJM transmission owner retail territory",
        np.where(in_pjm_state,
                 "PJM state, but no PJM utility serves this county at retail "
                 "(likely interconnects to transmission crossing the county)",
                 "plant is outside the PJM states - EIA balancing-authority code suspect"))
    out["zone_confidence"] = np.where(zoned, out.zone_confidence.fillna("high"), "unresolved")
    return out


# ---------------------------------------------------------------- main
def main():
    df = new_builds()
    df["cod_precision"] = "month"
    df["cod_date"] = pd.to_datetime(
        dict(year=df["Operating Year"].astype(int),
             month=df["Operating Month"].fillna(1).astype(int), day=1), errors="coerce")

    m = measured_cf()
    df = attach_cf(df, m)
    df = add_zone(df)
    df["annual_mwh_est"] = (df["delta_mw"] * df["capacity_factor_est"] * 8760).round(0)
    df["storage_duration_h"] = np.where(
        df["Technology"].isin(STORAGE_TECH) & df["delta_mw"].gt(0),
        (df["Nameplate Energy Capacity (MWh)"] / df["delta_mw"]).round(2), np.nan)

    ren = {"Entity Name": "owner", "Entity ID": "eia_entity_id", "Plant ID": "eia_plant_id",
           "Plant Name": "plant_name", "Generator ID": "generator_id", "Unit Code": "unit_code",
           "Plant State": "state", "County": "county", "Sector": "sector",
           "Technology": "technology", "Energy Source Code": "energy_source",
           "Prime Mover Code": "prime_mover", "Nameplate Capacity (MW)": "unit_nameplate_mw",
           "Net Summer Capacity (MW)": "net_summer_mw", "Net Winter Capacity (MW)": "net_winter_mw",
           "Nameplate Energy Capacity (MWh)": "storage_mwh", "Latitude": "latitude",
           "Longitude": "longitude", "Status": "eia_status", "_status_grp": "status",
           "delta_mw": "capacity_added_mw"}
    df = df.rename(columns=ren)
    cols = ["record_type", "site", "plant_name", "generator_id", "unit_code", "owner", "technology",
            "energy_source", "prime_mover", "cod_date", "cod_precision", "capacity_added_mw",
            "unit_nameplate_mw", "net_summer_mw", "net_winter_mw", "storage_mwh",
            "storage_duration_h", "capacity_factor_est", "cf_method", "annual_mwh_est",
            "state", "county", "pjm_zone", "zone_alts", "zone_confidence", "zone_basis",
            "latitude", "longitude", "sector", "status", "eia_plant_id", "eia_entity_id"]
    cols = [c for c in dict.fromkeys(cols) if c in df.columns]
    out = df[cols].sort_values(["cod_date", "capacity_added_mw"], ascending=[True, False])
    out.to_csv("output/pjm_projects_online_2015_2026.csv", index=False)

    tot = out.capacity_added_mw.sum()
    print("records %s | capacity added %s MW (%.2f GW)"
          % (f"{len(out):,}", f"{tot:,.0f}", tot / 1000))
    for st, s in out.groupby("site"):
        print("  %-24s %5s records %10s MW" % (st, f"{len(s):,}", f"{s.capacity_added_mw.sum():,.0f}"))
    print("\nCF basis:")
    print("  measured    %4d records %9.0f MW" % (
        out.cf_method.str.startswith("measured").sum(),
        out.loc[out.cf_method.str.startswith("measured"), "capacity_added_mw"].sum()))
    print("  benchmarked %4d records %9.0f MW" % (
        out.cf_method.str.startswith("benchmark").sum(),
        out.loc[out.cf_method.str.startswith("benchmark"), "capacity_added_mw"].sum()))
    print("  storage n/a %4d records %9.0f MW" % (
        out.cf_method.str.startswith("n/a").sum(),
        out.loc[out.cf_method.str.startswith("n/a"), "capacity_added_mw"].sum()))
    print("\nfootprint check (MW):")
    print(out.groupby("zone_basis").capacity_added_mw.agg(["size", "sum"]).round(0).to_string())
    print("\nzone (MW):")
    print(out.groupby("pjm_zone").capacity_added_mw.agg(["size", "sum"])
             .sort_values("sum", ascending=False).round(0).to_string())
    print("\n-> output/pjm_projects_online_2015_2026.csv")


if __name__ == "__main__":
    main()
