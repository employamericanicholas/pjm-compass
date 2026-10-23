"""Shared loader for EIA-860M vintages.

The header row moves between vintages, so we sniff for it on a
small read and then parse the sheet once. Parsed sheets are cached to CSV under
data/interim/cache/ because these workbooks are slow to open.
"""
import os

import pandas as pd

NUM = ['Plant ID', 'Nameplate Capacity (MW)', 'Net Summer Capacity (MW)',
       'Net Winter Capacity (MW)', 'Operating Month', 'Operating Year',
       'Retirement Month', 'Retirement Year', 'Nameplate Energy Capacity (MWh)',
       'DC Net Capacity (MW)', 'Latitude', 'Longitude']

CACHE = "data/interim/cache"

# The newest 860M vintage drives the unit inventory; bump these together on refresh.
LATEST = "data/raw/eia860m_sep2026.xlsx"
LATEST_LABEL = "2026-09"
LATEST_Y, LATEST_M = 2026, 9


def _clean(c):
    # 2016-17 vintages prefix headers with line breaks before the name
    return " ".join(str(c).split())


def _sniff_header(path, sheet):
    probe = pd.read_excel(path, sheet_name=sheet, header=None, nrows=6)
    for i in range(len(probe)):
        row = [_clean(v) for v in probe.iloc[i].tolist()]
        if ("Plant ID" in row or "Plant Code" in row) and "Nameplate Capacity (MW)" in row:
            return i
    raise RuntimeError("no header row found in %s [%s]" % (path, sheet))


def load(path, sheet="Operating", use_cache=True):
    os.makedirs(CACHE, exist_ok=True)
    ck = os.path.join(CACHE, "%s__%s.csv" % (os.path.basename(path).replace(".xlsx", ""), sheet))
    if use_cache and os.path.exists(ck) and os.path.getmtime(ck) > os.path.getmtime(path):
        d = pd.read_csv(ck, low_memory=False)
    else:
        d = pd.read_excel(path, sheet_name=sheet, header=_sniff_header(path, sheet))
        d.columns = [_clean(c) for c in d.columns]
        # the annual EIA-860 generator schedule (used as the end-2014 baseline) says
        # "Plant Code" where 860M says "Plant ID"
        d = d.rename(columns={"Plant Code": "Plant ID"})
        d.to_csv(ck, index=False)
    for c in NUM:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d[d["Plant ID"].notna()].copy()
    d["key"] = (d["Plant ID"].astype("Int64").astype(str) + "_" +
                d["Generator ID"].astype(str).str.strip().str.upper())
    return d
