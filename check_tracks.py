"""Before the RQ1 grid: are the track limits tight at all?

    python check_tracks.py

For every instance: tracks available (classification capacity / 76) against tracks the
unconstrained plan needs (ceil(cars / 200) per service), station by station.
"""
from model import solve
from read_data import read_data
from rq1_experiments import DATA, INSTANCES, set_tracks

for instance in INSTANCES:
    data = set_tracks(read_data(DATA / instance))
    result = solve(data, policy="mixed")  # no track limit
    print()
    print(instance)
    print("  station  needed  available  use")
    for v in data["stations"]:
        if v in data["tracks"]:
            needed, available = result["tracks_used"][v], data["tracks"][v]
            use = needed / available if available else float("inf")
            print("  %7s  %6d  %9d  %3.0f %%" % (v, needed, available, 100 * use))