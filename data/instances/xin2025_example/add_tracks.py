"""Add the tracks column to nodes.csv of the 8-station case (run once).

Tracks = classification capacity (Table 10 of Xin, Wu & Wang 2025) / 76 cars per track per day,
rounded down: read_data.tracks_from_capacity(), the same rule as in all other scripts.

    python data/instances/xin2025_example/add_tracks.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2].parent))  # the repository folder
from read_data import tracks_from_capacity  # noqa: E402

path = Path(__file__).parent / "nodes.csv"
nodes = pd.read_csv(path, dtype={"id": str})
nodes["tracks"] = nodes["classification_capacity"].map(tracks_from_capacity)
nodes.to_csv(path, index=False)
print(nodes[["id", "classification_capacity", "tracks"]])
