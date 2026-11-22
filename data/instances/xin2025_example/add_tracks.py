"""Add the tracks column to nodes.csv of the 8-station case (run once).

Tracks = classification capacity (Table 10 of Xin, Wu & Wang 2025) / 76 cars per track per day
(Maschen; data/german/AMORE_network_data.xlsx, sheet Assumptions).

    python data/instances/xin2025_example/add_tracks.py
"""
from pathlib import Path

import pandas as pd

TRACKS_THROUGHPUT = 76  # cars per track per day

path = Path(__file__).parent / "nodes.csv"
nodes = pd.read_csv(path, dtype={"id": str})
nodes["tracks"] = (nodes["classification_capacity"] / TRACKS_THROUGHPUT).round().astype(int)
nodes.to_csv(path, index=False)
print(nodes[["id", "classification_capacity", "tracks"]])