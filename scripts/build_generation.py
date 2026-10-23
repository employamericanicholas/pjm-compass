"""Measured net generation, by year, from every new-build project since it came online.

EIA-923 reports generation by plant x prime mover, not by generator, so a 2015+ unit
that shares a plant with older units of the same kind cannot be read off directly.
Each plant / prime-mover group is therefore handled one of two ways:

  * every unit in the group came online 2015+  -> the group's generation is the
    project's, including any pre-COD test energy;
  * the group also holds older units           -> the project gets the capacity share
    its units hold in each month they are online, and nothing before COD.

Uprates are left out: a few extra MW on an existing turbine have no separable output.
Storage is kept but its EIA net generation is net of charging, so it runs negative.
"""
import numpy as np
import pandas as pd

from build_projects import pm_group
from eia860m import LATEST, load

SRC = "output/pjm_projects_online_2015_2026.csv"
OUT_LONG = "output/pjm_generation_by_project_year.csv"
OUT_TECH = "output/summary_generation_by_year.csv"


def plant_generation():
    raw = pd.read_csv("data/interim/gen_monthly.csv.gz")
    # (fuel = ALL, prime mover = X) rollups are absent from this dataset, so sum the
    # fuel-level rows; the (ALL, ALL) plant totals would double-count prime movers
    g = raw[(raw.fuel2002 != "ALL") & (raw.primeMover != "ALL")].copy()
    g["pmg"] = g.primeMover.map(pm_group)
    g["m"] = pd.PeriodIndex(g.period, freq="M")
    return g.groupby(["plantCode", "pmg", "m"], as_index=False)["generation"].sum()


def inventory():
    """Every unit ever at these plants, with the months it was online."""
    op = load(LATEST, "Operating")
    rt = load(LATEST, "Retired")
    d = pd.concat([op, rt], ignore_index=True).drop_duplicates("key")
    d["pmg"] = d["Prime Mover Code"].map(pm_group)
    d["start"] = pd.PeriodIndex.from_fields(
        year=d["Operating Year"].fillna(1900).astype(int),
        month=d["Operating Month"].fillna(1).astype(int), freq="M")
    ret = d["Retirement Year"].notna()
    d["end"] = pd.Period("2100-01", "M")
    d.loc[ret, "end"] = pd.PeriodIndex.from_fields(
        year=d.loc[ret, "Retirement Year"].astype(int),
        month=d.loc[ret, "Retirement Month"].fillna(12).astype(int), freq="M")
    return d[["key", "Plant ID", "pmg", "start", "end", "Nameplate Capacity (MW)"]]


def main():
    p = pd.read_csv(SRC, parse_dates=["cod_date"])
    nb = p[p.record_type == "new build"].copy()
    nb["key"] = (nb.eia_plant_id.astype(int).astype(str) + "_" +
                 nb.generator_id.astype(str).str.strip().str.upper())
    nb["pmg"] = nb.prime_mover.map(pm_group)
    nb["start"] = nb.cod_date.dt.to_period("M")
    new_keys = set(nb.key)

    inv = inventory()
    inv = inv[inv["Plant ID"].isin(nb.eia_plant_id.unique())]
    inv["is_new"] = inv.key.isin(new_keys)
    mixed = inv[~inv.is_new].groupby(["Plant ID", "pmg"]).size()
    mixed = set(mixed.index)

    gen = plant_generation()
    gen = gen[gen.plantCode.isin(nb.eia_plant_id.unique())]
    months = sorted(gen.m.unique())

    rows = []
    for (pid, pmg), units in nb.groupby(["eia_plant_id", "pmg"]):
        gg = gen[(gen.plantCode == pid) & (gen.pmg == pmg)].set_index("m")["generation"]
        if gg.empty:
            continue
        is_mixed = (pid, pmg) in mixed
        allu = inv[(inv["Plant ID"] == pid) & (inv.pmg == pmg)]
        for m, mwh in gg.items():
            on_new = units[units.start <= m]
            if is_mixed:
                on_all = allu[(allu.start <= m) & (allu.end > m)]
                tot = on_all["Nameplate Capacity (MW)"].sum()
                share = on_new.capacity_added_mw.sum() / tot if tot > 0 else 0.0
                share = min(share, 1.0)
            else:
                share = 1.0
                if on_new.empty:          # test energy before the first COD
                    on_new = units
            if share == 0 or on_new.empty:
                continue
            w = on_new.capacity_added_mw / on_new.capacity_added_mw.sum()
            for k, wk in zip(on_new.key, w):
                rows.append((k, m.year, m, mwh * share * wk, is_mixed))

    a = pd.DataFrame(rows, columns=["key", "year", "m", "mwh", "mixed"])
    a = a.merge(nb[["key", "eia_plant_id", "plant_name", "technology"]], on="key")
    by = (a.groupby(["eia_plant_id", "plant_name", "year"], as_index=False)
           .agg(mwh=("mwh", "sum"), months_reported=("m", "nunique"),
                pro_rated=("mixed", "max")))
    by["mwh"] = by.mwh.round(0)
    by["attribution"] = np.where(by.pro_rated, "capacity share of a plant with older units",
                                 "whole plant / prime mover is 2015+ build")
    by.drop(columns="pro_rated").to_csv(OUT_LONG, index=False)

    # technology totals, with coverage: how much of the capacity online each year
    # actually has 923 generation behind it
    last = max(months)
    t = a.groupby(["year", "technology"], as_index=False)["mwh"].sum()
    t["twh"] = (t.mwh / 1e6).round(3)
    piv = t.pivot_table(index="year", columns="technology", values="twh", fill_value=0)
    piv["TOTAL"] = piv.sum(axis=1)
    cov = []
    for y in piv.index:
        end = pd.Period("%d-12" % y, "M") if y < last.year else last
        on = nb[nb.start <= end]
        reported = set(a.loc[a.year == y, "key"])
        cov.append(round(100 * on[on.key.isin(reported)].capacity_added_mw.sum()
                         / on.capacity_added_mw.sum(), 1))
    piv["pct_mw_reporting"] = cov
    piv["months"] = [12 if y < last.year else last.month for y in piv.index]
    piv.round(3).to_csv(OUT_TECH)

    print("generation data through %s" % last)
    print("projects with generation: %d of %d new-build plants"
          % (by.eia_plant_id.nunique(), nb.eia_plant_id.nunique()))
    print("pro-rated (plant also holds older units): %d plants"
          % by[by.pro_rated].eia_plant_id.nunique())
    print("\nTWh by year from 2015+ new build:")
    print(piv[["TOTAL", "pct_mw_reporting", "months"]].to_string())
    print("\n-> %s\n-> %s" % (OUT_LONG, OUT_TECH))


if __name__ == "__main__":
    main()
