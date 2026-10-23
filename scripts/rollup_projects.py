"""Collapse the generator-level table to one row per project.

EIA reports per generator, so a three-unit combined-cycle plant is three rows. For a
project list you want the plant.
"""
import numpy as np
import pandas as pd

SRC = "output/pjm_projects_online_2015_2026.csv"
OUT = "output/pjm_projects_rollup.csv"


def main():
    p = pd.read_csv(SRC, parse_dates=["cod_date"])
    p["_w"] = p.capacity_added_mw.fillna(0)
    p["_cfw"] = p._w * p.capacity_factor_est

    def agg(g):
        # Capacity-weight the CF over only the units that have one, so a solar+storage
        # hybrid is not credited with a battery's blank as if it were a zero.
        rated = g[g.capacity_factor_est.notna()]
        rated_mw = rated._w.sum()
        cf = rated._cfw.sum() / rated_mw if rated_mw > 0 else np.nan
        mw = g._w.sum()
        techs = sorted(t for t in g.technology.dropna().unique())
        if len(techs) == 1:
            tech = techs[0]
        else:   # hybrid site: name the components rather than picking the modal one
            tech = "Hybrid: " + " + ".join(techs)
        return pd.Series({
            "owner": g.owner.mode().iat[0] if not g.owner.mode().empty else g.owner.iat[0],
            "technology": tech,
            "site": g.site.iat[0],
            "units": len(g),
            "capacity_added_mw": round(mw, 1),
            "net_summer_mw": round(g.net_summer_mw.sum(), 1),
            "first_unit_online": g.cod_date.min(),
            "last_unit_online": g.cod_date.max(),
            "cod_precision": g.cod_precision.mode().iat[0],
            "capacity_factor_est": round(cf, 4) if pd.notna(cf) else np.nan,
            "cf_method": g.cf_method.mode().iat[0],
            "cf_covers_mw": round(rated_mw, 1),
            "annual_mwh_est": round(g.annual_mwh_est.sum(), 0),
            "storage_mwh": round(g.storage_mwh.sum(), 1) if g.storage_mwh.notna().any() else np.nan,
            "state": g.state.iat[0],
            "county": g.county.iat[0],
            "pjm_zone": g.pjm_zone_final.iat[0] if "pjm_zone_final" in g else g.pjm_zone.iat[0],
            "interconnecting_utility": (g.interconnecting_utility.iat[0]
                                        if "interconnecting_utility" in g else np.nan),
            "zone_source": g.zone_source.iat[0] if "zone_source" in g else np.nan,
            "grid_voltage_kv": g.grid_voltage_kv.iat[0] if "grid_voltage_kv" in g else np.nan,
            "lead_equity_owner": (g.lead_equity_owner.iat[0]
                                  if "lead_equity_owner" in g else np.nan),
            "equity_owners": g.equity_owners.iat[0] if "equity_owners" in g else np.nan,
            "zone_alts": g.zone_alts.iat[0],
            "zone_confidence": g.zone_confidence.iat[0],
            "zone_basis": g.zone_basis.iat[0],
            "latitude": g.latitude.iat[0],
            "longitude": g.longitude.iat[0],
            "sector": g.sector.iat[0],
            "status": g.status.mode().iat[0],
        })

    r = (p.groupby(["eia_plant_id", "plant_name", "record_type"], dropna=False)
          .apply(agg, include_groups=False)
          .reset_index()
          .sort_values(["first_unit_online", "capacity_added_mw"], ascending=[True, False]))
    r.to_csv(OUT, index=False)

    print("projects (plant x event): %d | capacity %.2f GW" % (len(r), r.capacity_added_mw.sum() / 1000))
    print("  new plants %d | units added at pre-2015 plants %d"
          % ((r.site == "new plant").sum(), (r.site != "new plant").sum()))
    print("\nsize distribution of new-build projects:")
    nb = r[r.record_type == "new build"]
    bins = [0, 5, 20, 100, 500, 1e9]
    labs = ["<5 MW", "5-20 MW", "20-100 MW", "100-500 MW", ">=500 MW"]
    nb = nb.assign(band=pd.cut(nb.capacity_added_mw, bins=bins, labels=labs, right=False))
    print(nb.groupby("band", observed=True).agg(
        projects=("plant_name", "size"), gw=("capacity_added_mw", lambda s: s.sum() / 1000)
    ).round(2).to_string())
    print("\n-> %s" % OUT)
    print("\n=== 30 LARGEST PROJECTS ===")
    cols = ["plant_name", "owner", "technology", "first_unit_online", "capacity_added_mw",
            "state", "pjm_zone", "capacity_factor_est"]
    print(r.nlargest(30, "capacity_added_mw")[cols].to_string(index=False))


if __name__ == "__main__":
    main()
