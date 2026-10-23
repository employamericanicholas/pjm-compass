"""Map (state, county) -> PJM footprint + transmission zone from EIA-861.

Two separate questions, answered from two different EIA-861 tables:

1. Is this county inside PJM at all?
   EIA-861 Utility_Data carries a per-utility "operating in PJM" RTO flag. Joining
   that to Service_Territory (utility -> county) gives the PJM footprint directly,
   rather than inferring it from transmission owners alone. This matters because
   EIA-860M assigns Balancing Authority = PJM to some plants that sit well outside
   the footprint, and those need flagging rather than silent inclusion.

2. Which transmission zone does it sit in?
   PJM settles by transmission zone, so we match the incumbent transmission owners'
   service territories. Co-ops and munis are mapped to the zone they take service in.

Uses the 2023 vintage: in 2024 FirstEnergy consolidated Met-Ed, Penelec, Penn Power
and West Penn Power into one filing, collapsing zones PJM still settles separately.
"""
import difflib
import re
import zipfile

import pandas as pd

ZIP, YR = "data/raw/f8612023.zip", 2023

# zone -> (regex on EIA-861 utility name, states where that match is valid)
ZONE_UTILS = {
    "AECO":      (r"^Atlantic City Electric", {"NJ"}),
    "AEP":       (r"^(Appalachian Power|Ohio Power|Indiana Michigan Power|Kentucky Power|Wheeling Power)",
                  {"OH", "WV", "VA", "KY", "TN", "IN", "MI"}),
    "APS":       (r"^(Monongahela Power|The Potomac Edison|Potomac Edison|West Penn Power)",
                  {"WV", "MD", "PA", "VA"}),
    # Pennsylvania Power Co is a FirstEnergy sub whose transmission sits in the ATSI zone
    "ATSI":      (r"^(Ohio Edison|Cleveland Electric Illum|Toledo Edison|Pennsylvania Power Co)",
                  {"OH", "PA"}),
    "BGE":       (r"^Baltimore Gas", {"MD"}),
    "ComEd":     (r"^Commonwealth Edison", {"IL"}),
    "DAY":       (r"^(Dayton Power|AES Ohio)", {"OH"}),
    "DEOK":      (r"^Duke Energy (Ohio|Kentucky)", {"OH", "KY"}),
    "DLCO":      (r"^Duquesne Light", {"PA"}),
    "DPL":       (r"^Delmarva Power", {"DE", "MD", "VA"}),
    "Dominion":  (r"^Virginia Electric", {"VA", "NC", "WV"}),
    "JCPL":      (r"^Jersey Central Power", {"NJ"}),
    "METED":     (r"^Metropolitan Edison", {"PA"}),
    "PECO":      (r"^PECO Energy", {"PA"}),
    "PENELEC":   (r"^Pennsylvania Electric", {"PA"}),
    "PEPCO":     (r"^Potomac Electric Power", {"MD", "DC"}),
    "PPL":       (r"^PPL Electric", {"PA"}),
    "PSEG":      (r"^Public Service (Electric|Elec)", {"NJ"}),
    "RECO":      (r"^Rockland Electric", {"NJ"}),
    "SMECO":     (r"^Southern Maryland Elec", {"MD"}),
}

# Co-ops / munis that take transmission service in a known zone but whose counties
# no transmission owner serves at retail. EKPC is its own PJM zone.
COOP_ZONE = {
    r"^(Rappahannock Electric|Shenandoah Valley Elec|Northern Virginia Elec|"
    r"Central Virginia Elec|Prince George Electric|Community Electric|"
    r"Mecklenburg Electric|Southside Electric|Northern Neck Elec)": ("Dominion", {"VA"}),
    r"^(A & N Electric|Choptank Electric|Delaware Electric Coop)": ("DPL", {"VA", "MD", "DE"}),
    r"^(Harrison Rural|BARC Electric|Craig-Botetourt)": ("APS", {"WV", "VA"}),
    r"^(Big Sandy RECC|Blue Grass Energy|Clark Energy|Cumberland Valley Elec|Farmers RECC|"
    r"Fleming-Mason Energy|Grayson RECC|Inter-County Energy|Jackson Energy|Licking Valley RECC|"
    r"Nolin RECC|Owen Electric|Salt River Electric|Shelby Energy|South Kentucky RECC|"
    r"Taylor County RECC)": ("EKPC", {"KY"}),
}

# Applied only where several zones share a county; documented as medium confidence.
PRIORITY = ["Dominion", "ComEd", "PSEG", "PEPCO", "BGE", "PECO", "PPL", "JCPL", "AECO",
            "DPL", "SMECO", "METED", "PENELEC", "DLCO", "APS", "ATSI",
            "DAY", "DEOK", "AEP", "EKPC", "RECO"]


def norm_county(c):
    c = str(c).strip().lower()
    c = re.sub(r"\b(county|parish|census area|municipality|city and borough|borough)\b", " ", c)
    c = re.sub(r"\bcity\b", " ", c)          # VA independent cities: "Danville City" -> "danville"
    c = re.sub(r"\bst\.?\b", "saint", c)
    return re.sub(r"[^a-z]", "", c)


def load(member, header=0):
    with zipfile.ZipFile(ZIP).open(member) as f:
        return pd.read_excel(f, header=header)


def main():
    st = load("Service_Territory_%d.xlsx" % YR)
    st.columns = ["data_year", "utility_id", "utility_name", "short_form", "state", "county"]
    st["utility_name"] = st["utility_name"].astype(str).str.strip()
    st["state"] = st["state"].astype(str).str.strip().str.upper()
    st["county_key"] = st["county"].map(norm_county)

    # ---- 1. PJM footprint, from the RTO participation flags
    ud = load("Utility_Data_%d.xlsx" % YR, header=1)
    ud.columns = [str(c).strip() for c in ud.columns]
    ud = ud.rename(columns={"Utility Number": "utility_id", "PJM": "in_pjm"})
    pjm_ids = set(ud.loc[ud["in_pjm"].astype(str).str.upper().eq("Y"), "utility_id"].dropna())
    print("utilities flagged as operating in PJM: %d" % len(pjm_ids))

    foot = st[st["utility_id"].isin(pjm_ids)]
    footprint = foot[["state", "county_key"]].drop_duplicates()
    footprint["in_pjm_footprint"] = True
    print("counties in PJM footprint: %d across %d states"
          % (len(footprint), footprint.state.nunique()))
    print("  by state:", footprint.state.value_counts().to_dict())

    # ---- 2. transmission zone assignment
    rows = []
    for zone, (pat, states) in ZONE_UTILS.items():
        m = st[st["utility_name"].str.contains(pat, case=False, regex=True, na=False)
               & st["state"].isin(states)]
        if m.empty:
            print("!! %s: NO MATCH" % zone)
        for _, r in m.iterrows():
            rows.append({"zone": zone, "state": r["state"], "county_key": r["county_key"],
                         "utility": r["utility_name"], "via": "transmission owner"})
        print("%-10s utils=%2d rows=%4d" % (zone, m["utility_name"].nunique(), len(m)))

    for pat, (zone, states) in COOP_ZONE.items():
        m = st[st["utility_name"].str.contains(pat, case=False, regex=True, na=False)
               & st["state"].isin(states)]
        for _, r in m.iterrows():
            rows.append({"zone": zone, "state": r["state"], "county_key": r["county_key"],
                         "utility": r["utility_name"], "via": "co-op/muni"})
        print("%-10s (co-op) utils=%2d rows=%4d" % (zone, m["utility_name"].nunique(), len(m)))

    cz = pd.DataFrame(rows).drop_duplicates()
    cz.to_csv("data/interim/zone_county_long.csv", index=False)

    prio = {z: i for i, z in enumerate(PRIORITY)}
    to_only = cz[cz.via == "transmission owner"]
    g = (cz.groupby(["state", "county_key"])
           .agg(zones=("zone", lambda s: sorted(set(s))))
           .reset_index())
    to_zones = (to_only.groupby(["state", "county_key"])["zone"]
                       .apply(lambda s: sorted(set(s))).to_dict())
    # prefer a transmission owner's own zone over a co-op-inferred one
    def pick(r):
        cands = to_zones.get((r["state"], r["county_key"]), r["zones"])
        return sorted(cands, key=lambda z: prio.get(z, 99))[0]
    g["pjm_zone"] = g.apply(pick, axis=1)
    g["n_zones"] = g["zones"].str.len()
    g["zone_alts"] = g["zones"].apply(lambda zs: "; ".join(zs))
    g["zone_confidence"] = g["n_zones"].map(lambda n: "high" if n == 1 else "medium")

    out = g.merge(footprint, on=["state", "county_key"], how="outer")
    out["in_pjm_footprint"] = out["in_pjm_footprint"].fillna(False)
    out["pjm_zone"] = out["pjm_zone"].fillna("zone undetermined")
    out["zone_confidence"] = out["zone_confidence"].fillna("low")
    out.drop(columns=["zones"]).to_csv("data/interim/county_to_zone.csv", index=False)

    print("\ncounties with a zone: %d (single %d / multi %d)"
          % (int(g.shape[0]), int((g.n_zones == 1).sum()), int((g.n_zones > 1).sum())))
    print("rows written: %d" % len(out))
    print("\nprimary zone assignment counts:")
    print(out[out.pjm_zone != "zone undetermined"].pjm_zone.value_counts().to_string())

    # county-name fuzzy fallback table, for EIA typos like "Prince Geroges"
    alias = []
    for state, sub in st.groupby("state"):
        keys = sorted(sub.county_key.unique())
        alias.append(pd.DataFrame({"state": state, "county_key": keys}))
    pd.concat(alias).to_csv("data/interim/valid_counties.csv", index=False)


if __name__ == "__main__":
    main()
