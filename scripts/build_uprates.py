"""Detect and date PJM capacity uprates 2015-2026 by walking EIA-860M vintages.

EIA does not publish uprates as records, so we track each generator's nameplate
rating across successive vintages and attribute each step change to the interval
in which it appeared. Generators whose first appearance is 2015+ are new builds,
not uprates, and are excluded here.

860M only begins mid-2015, and its Dec 2015 vintage carries no nameplate column, so the
end-2014 baseline is the annual EIA-860 generator schedule and the first step spans
2014-12 to 2016-12.
"""
import pandas as pd
from eia860m import LATEST, LATEST_LABEL, load

VINTAGES = [("2014-12","data/raw/eia860_2014_generator.xlsx","Operable"),
            ("2016-12","data/raw/eia860m_dec2016.xlsx"),
            ("2017-12","data/raw/eia860m_dec2017.xlsx"),
            ("2018-12","data/raw/eia860m_dec2018.xlsx"),
            ("2019-12","data/raw/eia860m_dec2019.xlsx"),
            ("2020-12","data/raw/eia860m_dec2020.xlsx"),
            ("2021-12","data/raw/eia860m_dec2021.xlsx"),
            ("2022-12","data/raw/eia860m_dec2022.xlsx"),
            ("2023-12","data/raw/eia860m_dec2023.xlsx"),
            ("2024-12","data/raw/eia860m_dec2024.xlsx"),
            ("2025-12","data/raw/eia860m_dec2025.xlsx"),
            ("2026-07","data/raw/eia860m_july2026.xlsx"),
            (LATEST_LABEL, LATEST)]

MIN_MW = 1.0        # ignore sub-MW rounding noise
MIN_PCT = 0.01      # and changes under 1% of the unit

def main():
    snaps = {}
    for label, path, *sheet in VINTAGES:
        d = load(path, *sheet)
        d = d.drop_duplicates("key").set_index("key")
        snaps[label] = d
        print(f"{label}: {len(d):,} operating gens")

    latest = snaps[LATEST_LABEL]
    pjm = latest[latest["Balancing Authority Code"] == "PJM"].index
    base = snaps["2014-12"]
    # uprate candidates: in PJM today AND already operating at end-2014
    cand = [k for k in pjm if k in base.index]
    print(f"\nPJM generators operating at end-2014 and still operating: {len(cand):,}")

    recs = []
    labels = [v[0] for v in VINTAGES]
    for k in cand:
        prev = base.at[k, "Nameplate Capacity (MW)"]
        if pd.isna(prev):
            continue
        for i in range(1, len(labels)):
            lab = labels[i]
            s = snaps[lab]
            if k not in s.index:
                continue
            cur = s.at[k, "Nameplate Capacity (MW)"]
            if pd.isna(cur):
                continue
            d = cur - prev
            if abs(d) >= MIN_MW and prev > 0 and abs(d) / prev >= MIN_PCT:
                row = latest.loc[k]
                recs.append({
                    "key": k, "detected_by": lab, "prev_vintage": labels[i-1],
                    "mw_before": prev, "mw_after": cur, "delta_mw": d,
                    "plant_id": row["Plant ID"], "plant_name": row["Plant Name"],
                    "generator_id": row["Generator ID"], "owner": row["Entity Name"],
                    "technology": row["Technology"], "state": row["Plant State"],
                    "county": row["County"],
                })
                prev = cur

    up = pd.DataFrame(recs)
    up["change_type"] = up["delta_mw"].map(lambda d: "uprate" if d > 0 else "derate")
    up.to_csv("data/interim/capacity_changes.csv", index=False)

    u = up[up.change_type == "uprate"]; dr = up[up.change_type == "derate"]
    print(f"\nUPRATE events : {len(u):>4}  +{u.delta_mw.sum():>9,.1f} MW  ({u.key.nunique()} generators)")
    print(f"DERATE events : {len(dr):>4}  {dr.delta_mw.sum():>10,.1f} MW  ({dr.key.nunique()} generators)")
    print(f"NET           :       {up.delta_mw.sum():>+10,.1f} MW")
    print("\nUprate MW by detection vintage (i.e. when the change first appeared):")
    print(u.groupby("detected_by")["delta_mw"].agg(["count","sum"]).round(1).to_string())
    print("\nUprate MW by technology:")
    print(u.groupby("technology")["delta_mw"].agg(["count","sum"]).sort_values("sum",ascending=False).round(1).to_string())

if __name__ == "__main__":
    main()
