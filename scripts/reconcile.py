"""Reconcile the bottom-up EIA build against PJM's public "23 GW since 2020" figure,
and emit the summary tables.

PJM's claim (Inside Lines, "Connected"): since 2020 PJM completed interconnection
agreements for 103 GW, of which ~23 GW actually went into service. That number is
not defined in the source, so rather than assert a single total we show which
measurement choices move ours toward it.
"""
import calendar

import pandas as pd

from eia860m import LATEST_M, LATEST_Y

SRC = "output/pjm_projects_online_2015_2026.csv"


def gw(x):
    return "%.2f" % (x / 1000.0)


def main():
    p = pd.read_csv(SRC, parse_dates=["cod_date"])
    nb = p[p.record_type == "new build"]

    # A genuine cumulative walk: each step keeps the previous step's restrictions.
    # Reporting these as independent slices overstates the intermediate rows, because
    # the same units then get removed twice.
    rows, step = [], p.copy()

    def add(label, frame, col="capacity_added_mw"):
        rows.append({"basis": label, "records": len(frame),
                     "GW": round(frame[col].sum() / 1000, 2)})

    add("All new units, nameplate, Jan 2015 - %s %d"
        % (calendar.month_abbr[LATEST_M], LATEST_Y), step)
    # PJM's figure counts from 2020, so the 2015-2019 build is the first thing off
    step = step[step.cod_date >= "2020-01-01"]
    add("  ... less 2015-2019 additions (PJM counts from 2020)", step)
    if "non_pjm_interconnection" in step.columns:
        step = step[step.non_pjm_interconnection.isna()]
        add("  ... less units reporting a non-PJM interconnection", step)
    step = step[step.cod_date < "2026-01-01"]
    add("  ... less 2026 additions (through Dec 2025)", step)
    # size is the plant's, not the unit's: a 45 MW plant built from 15 MW units stays in
    step = step[step.groupby("eia_plant_id").capacity_added_mw.transform("sum") >= 20]
    add("  ... less projects under 20 MW (queue scale)", step)
    add("  ... on NET SUMMER capacity  <- PJM-comparable basis", step, "net_summer_mw")

    rec = pd.DataFrame(rows)
    rec.to_csv("output/reconciliation.csv", index=False)
    print("=== RECONCILIATION TO PJM'S ~23 GW ===")
    print(rec.to_string(index=False))

    print("\n=== BY YEAR (nameplate MW added) ===")
    y = p.assign(year=p.cod_date.dt.year).pivot_table(
        index="year", columns="site", values="capacity_added_mw",
        aggfunc="sum", fill_value=0)
    y["total"] = y.sum(axis=1)
    y.loc["TOTAL"] = y.sum()
    print(y.round(0).to_string())
    y.round(1).to_csv("output/summary_by_year.csv")

    print("\n=== BY TECHNOLOGY ===")
    t = p.groupby("technology").agg(
        projects=("plant_name", "nunique"), units=("plant_name", "size"),
        mw=("capacity_added_mw", "sum"), cf=("capacity_factor_est", "median"),
        est_twh=("annual_mwh_est", lambda s: s.sum() / 1e6)).sort_values("mw", ascending=False)
    print(t.round(2).to_string())
    t.round(3).to_csv("output/summary_by_technology.csv")

    print("\n=== BY PJM TRANSMISSION ZONE ===")
    z = p.groupby("pjm_zone").agg(
        units=("plant_name", "size"), mw=("capacity_added_mw", "sum"),
        est_twh=("annual_mwh_est", lambda s: s.sum() / 1e6)).sort_values("mw", ascending=False)
    print(z.round(2).to_string())
    z.round(3).to_csv("output/summary_by_zone.csv")

    print("\n=== TOP 25 OWNERS BY CAPACITY ADDED ===")
    o = p.groupby("owner").agg(units=("plant_name", "size"),
                               mw=("capacity_added_mw", "sum")).nlargest(25, "mw")
    print(o.round(1).to_string())
    o.round(1).to_csv("output/summary_by_owner.csv")

    print("\n=== ENERGY CONTRIBUTION ===")
    twh = p.annual_mwh_est.sum() / 1e6
    print("estimated annual generation from all 2015-2026 additions: %.1f TWh" % twh)
    print("PJM annual load is roughly 800 TWh, so this is about %.1f%% of it" % (twh / 800 * 100))


if __name__ == "__main__":
    main()
