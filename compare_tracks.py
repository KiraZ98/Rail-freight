"""Compare the RQ1 runs without and with the track limit.

    python compare_tracks.py
"""
import pandas as pd

from rq1_experiments import RESULTS

key = ["instance", "demand_growth", "capacity_level", "policy"]
without = pd.read_csv(RESULTS / "rq1_runs.csv").set_index(key)
with_tracks = pd.read_csv(RESULTS / "rq1_runs_tracks.csv").set_index(key)

# 1. Is the limit active? Number of stations at their track limit, and the busiest station's use
active = with_tracks["track_limits_reached"].groupby(level=["demand_growth", "capacity_level"]).mean()
use = with_tracks["peak_track_utilisation"].groupby(level=["demand_growth", "capacity_level"]).mean()
print("Stations at their track limit (mean per run) and track use of the busiest station")
print(pd.DataFrame({"at_limit": active.round(2), "peak_use_%": (100 * use).round(0)}).to_string())

# 2. Does it change the advantage of mixed over intree?
def advantage(runs):
    profit = runs["profit"].unstack("policy")
    return (100 * (profit["mixed"] - profit["intree"]) / profit["intree"]) \
        .groupby(level=["demand_growth", "capacity_level"]).mean()

print()
print("Profit of mixed above intree (%, mean over instances)")
print(pd.DataFrame({"without_tracks": advantage(without).round(1),
                    "with_tracks": advantage(with_tracks).round(1)}).to_string())


# 3. Profit lost to the track limit, and blocks (services used) per policy
loss = 100 * (without["profit"] - with_tracks["profit"]) / without["profit"]
bad = loss[~(loss > -1e-6)]
if len(bad):
    print("Runs where the track limit seems to raise profit (or rows that do not match):")
    print(pd.DataFrame({
        "loss_%": bad,
        "profit_without": without.loc[bad.index, "profit"],
        "profit_with": with_tracks.loc[bad.index, "profit"],
        "status_without": without.loc[bad.index, "status"],
        "status_with": with_tracks.loc[bad.index, "status"],
        "gap_without": without.loc[bad.index, "gap"],
        "gap_with": with_tracks.loc[bad.index, "gap"],
    }).to_string())
    print("rows without / with:", len(without), len(with_tracks))