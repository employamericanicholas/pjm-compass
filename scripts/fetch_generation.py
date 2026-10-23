"""Pull EIA-923 plant-level monthly net generation for the PJM footprint via EIA API v2.

Starts in 2015 so every unit in the build list can be followed from its first month
online. States are fetched in parallel; the API tolerates a few concurrent readers.
"""
import json, os, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

STATES = ["PA","NJ","MD","DE","VA","WV","OH","IN","IL","MI","KY","NC","TN","DC"]
START, END = "2015-01", "2026-08"
BASE = "https://api.eia.gov/v2/electricity/facility-fuel/data/"

def key():
    for line in open(".eia_env"):
        if line.startswith("EIA_API_KEY="):
            return line.split("=",1)[1].strip()
    sys.exit("no EIA_API_KEY in .eia_env")

def fetch(k, state):
    out, offset = [], 0
    while True:
        q = [("api_key",k),("frequency","monthly"),("data[0]","generation"),
             ("start",START),("end",END),("length","5000"),("offset",str(offset)),
             ("facets[state][]",state)]
        url = BASE+"?"+urllib.parse.urlencode(q)
        for attempt in range(6):
            try:
                r = json.load(urllib.request.urlopen(url, timeout=180))["response"]
                break
            except Exception as e:
                if attempt == 5: raise
                time.sleep(3*(attempt+1))
        out.extend(r["data"])
        total = int(r["total"])
        offset += 5000
        print(f"  {state}: {min(offset,total)}/{total}", flush=True)
        if offset >= total: break
    return out

def main():
    k = key(); rows = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for part in ex.map(lambda s: fetch(k, s), STATES):
            rows.extend(part)
    df = pd.DataFrame(rows)
    df["generation"] = pd.to_numeric(df["generation"], errors="coerce")
    df["plantCode"]  = pd.to_numeric(df["plantCode"], errors="coerce").astype("Int64")
    df.to_csv("data/interim/gen_monthly.csv.gz", index=False, compression="gzip")
    print(f"\nwrote data/interim/gen_monthly.csv.gz  rows={len(df):,}  plants={df.plantCode.nunique():,}"
          f"  periods={df.period.min()}..{df.period.max()}")

if __name__ == "__main__":
    main()
