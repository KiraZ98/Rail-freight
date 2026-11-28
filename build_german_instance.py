"""Build the German network as model instances.

    python build_german_instance.py

Needs the output of data/german/build_distances.py (yard_coordinates.csv and
distance_matrix_km.csv in data/german). Writes one folder per demand seed to data/instances,
in the same format as the other instances, each with a SOURCES.md.

What comes from where:
* yards and their classification tracks: Bundestag Drucksache 19/26856 (sheet Yards)
* rail distances between yards: OpenStreetMap rail network (build_distances.py)
* yard capacity: tracks x 76 cars per track per day (sheet Assumptions; read_data.CARS_PER_TRACK_DAY)
* everything Germany has no published data for yet (goods categories, service classes, train
  costs, demand, revenues, time limits, waiting-time parameters): the base paper's own values
  and recipe, as for the random networks. Demand is therefore synthetic.
"""
import csv
import math
import random
from pathlib import Path

import pandas as pd

from generate_instance import CATEGORIES, CLASSES
from read_data import CARS_PER_TRACK_DAY

# ---- settings ----
GERMAN = Path(__file__).parent / "data" / "german"
OUTPUT = Path(__file__).parent / "data" / "instances"
N_DEMANDS = 80          # 4 per yard, the same ratio as the random networks of RQ1 (40 for 10 stations)
SEEDS = [1, 2, 3]       # one German network, three synthetic demand sets
MERGE = {"Seddin Süd": "Seddin"}  # 0.3 km apart, matched to the same rail point (distance 0 km)

# Waiting-time parameters: no German source. The base paper's real-world case (Section 6.3.1)
# gives the average over its 139 stations: accumulation 0.04 h, transfer 0.02 h.
ACCUMULATION_TIME_H = 0.04
TRANSFER_TIME_H = 0.02


def read_yards():
    """The model yards (top N by tracks) with tracks, coordinates and rail distances."""
    xlsx = GERMAN / "AMORE_network_data.xlsx"
    yards = pd.read_excel(xlsx, sheet_name="Yards")
    yards = yards[pd.to_numeric(yards["Rank"], errors="coerce").notna()].copy()
    yards["Rank"] = yards["Rank"].astype(int)
    top_n = int(pd.read_excel(xlsx, sheet_name="Assumptions", header=None).iloc[7, 1])
    yards = yards[yards["Rank"] <= top_n]

    coordinates = pd.read_csv(GERMAN / "yard_coordinates.csv")
    yards = yards.merge(coordinates[["Rank", "Latitude", "Longitude"]], on="Rank", suffixes=("_sheet", ""))
    distances = pd.read_csv(GERMAN / "distance_matrix_km.csv", index_col=0)
    method = (GERMAN / "distance_method.txt").read_text(encoding="utf-8").strip()

    missing = [y for y in yards["Yard"] if y not in distances.index]
    if missing or distances.isna().any().any():
        raise ValueError("distance matrix incomplete; run data/german/build_distances.py first: " + str(missing))

    # Yards that are parts of one site (same rail point, distance 0) become one node with their
    # tracks added up; otherwise wagons could move between them on a free 0 km link.
    for part, main in MERGE.items():
        if part in set(yards["Yard"]) and main in set(yards["Yard"]):
            tracks = yards.loc[yards["Yard"] == part, "Classification tracks"].iloc[0]
            yards.loc[yards["Yard"] == main, "Classification tracks"] += tracks
            yards.loc[yards["Yard"] == main, "Yard"] = main + " (incl. " + part.replace(main, "").strip() + ")"
            distances = distances.rename(index={main: main + " (incl. " + part.replace(main, "").strip() + ")"},
                                         columns={main: main + " (incl. " + part.replace(main, "").strip() + ")"})
            yards = yards[yards["Yard"] != part]
    return yards.sort_values("Rank").reset_index(drop=True), distances, method


def build(seed, yards, distances, method):
    rng = random.Random(seed)
    stations = [str(r) for r in yards["Rank"]]
    name = dict(zip(stations, yards["Yard"]))
    km = {(i, j): float(distances.loc[name[i], name[j]]) for i in stations for j in stations if i != j}

    folder = OUTPUT / ("german_V" + str(len(stations)) + "_D" + str(N_DEMANDS) + "_seed" + str(seed))
    folder.mkdir(parents=True, exist_ok=True)

    # ---- yards: tracks from the Bundestag answer, capacity = tracks x 76 ----
    nodes = []
    for _, r in yards.iterrows():
        capacity = int(r["Classification tracks"]) * CARS_PER_TRACK_DAY
        nodes.append([str(r["Rank"]), r["Yard"], ACCUMULATION_TIME_H, TRANSFER_TIME_H,
                      capacity, capacity, int(r["Classification tracks"]),
                      round(float(r["Latitude"]), 5), round(float(r["Longitude"]), 5)])

    # ---- services: every pair of yards in every class, on the rail distance ----
    services = []
    for (i, j), d in sorted(km.items(), key=lambda p: (int(p[0][0]), int(p[0][1]))):
        for c, (speed, size, factor) in CLASSES.items():
            services.append([i, j, c, round(d), round(50 * d * factor), ""])  # train cost: equation (49)

    # ---- demands: the recipe of Section 6.1.1, on the German yards and rail distances ----
    slowest = min(speed for (speed, size, factor) in CLASSES.values())
    possible = [(o, d, p) for o in stations for d in stations if o != d for p in range(len(CATEGORIES))]
    chosen = sorted(rng.sample(possible, N_DEMANDS), key=lambda k: (int(k[0]), int(k[1]), k[2]))
    demands = []
    for number, (o, d, p) in enumerate(chosen, 1):
        category, car_cost, express = CATEGORIES[p]
        volume = rng.randint(1, 200)
        if express:
            time_limit = round(1.2 * km[o, d] / slowest, 2)                         # equation (47)
            revenue = round(km[o, d] * volume * car_cost * rng.uniform(3, 4))       # equation (48)
        else:
            time_limit = ""
            revenue = round(km[o, d] * volume * car_cost * rng.uniform(2, 3))       # equation (48)
        demands.append(["d" + str(number).zfill(3), o, d, category, volume, time_limit, revenue])

    def write(filename, header, rows):
        with open(folder / filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(rows)

    write("nodes.csv", ["id", "name", "accumulation_time_h", "transfer_time_h", "classification_capacity",
                        "sorting_capacity", "tracks", "latitude", "longitude"], nodes)
    write("categories.csv", ["id", "express", "car_cost_per_car_km"],
          [[n, "yes" if e else "no", c] for (n, c, e) in CATEGORIES])
    write("service_classes.csv", ["id", "speed_kmh", "max_cars"],
          [[c, speed, size] for c, (speed, size, factor) in CLASSES.items()])
    write("services.csv", ["origin", "destination", "class", "mileage_km", "train_cost", "max_frequency"], services)
    write("demands.csv", ["id", "origin", "destination", "category", "cars_per_day", "time_limit_h", "revenue"], demands)
    (folder / "SOURCES.md").write_text(SOURCES.format(
        yards=len(stations), services=len(services), demands=N_DEMANDS, seed=seed, method=method,
        cars=CARS_PER_TRACK_DAY, acc=ACCUMULATION_TIME_H, tra=TRANSFER_TIME_H), encoding="utf-8", newline="\n")
    return folder


SOURCES = """# Sources: German network

Built by `build_german_instance.py`: {yards} German classification yards, {services} services,
{demands} demands, demand seed {seed}. Running the script again gives the same files.

| File / value | Source |
|---|---|
| Yards (`nodes.csv`: id = rank, name, `tracks`) | The 20 yards with the most classification tracks; Deutscher Bundestag, Drucksache 19/26856 (2021), answer to question 4 (sheet Yards of `data/german/AMORE_network_data.xlsx`). Seddin and Seddin Süd, 0.3 km apart and on the same rail point, are merged into one node with their tracks added up (40 + 20 = 60), which gives {yards} nodes |
| `latitude`, `longitude` | OpenStreetMap (Nominatim geocoding), `data/german/yard_coordinates.csv` |
| Classification and sorting capacity | tracks x {cars} cars per track per day. 76 = Maschen's shunting capacity of about 2 x 4,000 wagons per day (dpa via heise online, 18.08.2020) over its 105 tracks (Bundestag 19/26856); sheet Assumptions. One yard used as a proxy for all, and the same value for cars arriving and leaving: an assumption of ours |
| Accumulation / transfer time parameter | {acc} h / {tra} h: average of the 139 stations of the base paper's real-world case (Xin, Wu & Wang 2025, Section 6.3.1). Chinese values; no German source found |
| Service mileage | Rail distance between the yards. Method: {method} |
| Service classes, goods categories and car costs | As in the base paper (Section 6.2.1, Table 11) |
| Train cost | 50 x rail distance x 1.0 (ordinary), 1.1 (fast), 1.2 (express): equation (49) of the base paper |
| Maximal frequency | Left blank (no limit): no German source |
| Demands | Synthetic, recipe of the base paper (Section 6.1.1): random origin, destination and goods category; volume random in [1, 200] cars per day; time limit for express goods 1.2 x distance / slowest speed (47); revenue distance x volume x car cost x random(3, 4) for express, random(2, 3) otherwise (48). Distance is the rail distance |

Costs and revenues are in the base paper's units (CNY), so results are comparable with the other
instances but not real German prices. Real demand (Destatis GENESIS 46131) can replace the
synthetic demand later.
"""


if __name__ == "__main__":
    yards, distances, method = read_yards()
    print(len(yards), "yards; distances:", method)
    for seed in SEEDS:
        print("built", build(seed, yards, distances, method).name)
