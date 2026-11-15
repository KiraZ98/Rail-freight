"""Instance format: one folder per network instance.

    nodes.csv            id, name, reclass_capacity_cars_per_day, classification_tracks
    arcs.csv             from, to, length_km, line_capacity_trains_per_day   (undirected)
    demands.csv          id, origin, destination, category (express|bulk), cars_per_day, revenue_per_car
    service_classes.csv  id, speed_kmh, max_cars, train_cost_per_km
    params.json          scalar parameters (costs, cars_per_track, ...)

Only the standard library is used here, so loading works without Gurobi or pandas.
"""
from __future__ import annotations

import csv
import heapq
import json
from dataclasses import dataclass
from pathlib import Path

CATEGORIES = ("express", "bulk")


@dataclass(frozen=True)
class Yard:
    id: str
    name: str
    reclass_capacity: float  # cars per day
    tracks: int  # classification tracks


@dataclass(frozen=True)
class Arc:
    tail: str
    head: str
    length_km: float
    capacity: float  # trains per day


@dataclass(frozen=True)
class Demand:
    id: str
    origin: str
    destination: str
    category: str
    cars: float  # cars per day
    revenue_per_car: float


@dataclass(frozen=True)
class ServiceClass:
    id: str
    speed_kmh: float
    max_cars: int
    train_cost_per_km: float


@dataclass
class Instance:
    name: str
    yards: dict[str, Yard]
    arcs: list[Arc]  # directed: every row of arcs.csv appears in both directions
    demands: list[Demand]
    service_classes: dict[str, ServiceClass]
    params: dict

    @property
    def total_demand(self) -> float:
        return sum(d.cars for d in self.demands)

    def shortest_distances(self) -> dict[tuple[str, str], float]:
        """Shortest rail distance in km between every ordered pair of yards."""
        adj: dict[str, list[tuple[str, float]]] = {y: [] for y in self.yards}
        for a in self.arcs:
            adj[a.tail].append((a.head, a.length_km))
        dist: dict[tuple[str, str], float] = {}
        for src in self.yards:
            best = {src: 0.0}
            heap = [(0.0, src)]
            while heap:
                d, u = heapq.heappop(heap)
                if d > best[u]:
                    continue
                for v, w in adj[u]:
                    if d + w < best.get(v, float("inf")):
                        best[v] = d + w
                        heapq.heappush(heap, (d + w, v))
            for dst, d in best.items():
                if dst != src:
                    dist[src, dst] = d
        return dist

    def scaled(self, demand_factor: float = 1.0) -> "Instance":
        """Copy with all demand volumes multiplied (base, +25 %, +50 % scenarios)."""
        demands = [
            Demand(d.id, d.origin, d.destination, d.category, d.cars * demand_factor, d.revenue_per_car)
            for d in self.demands
        ]
        return Instance(self.name, self.yards, self.arcs, demands, self.service_classes, self.params)


def _rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_instance(folder: str | Path) -> Instance:
    folder = Path(folder)
    yards = {
        r["id"]: Yard(r["id"], r["name"], float(r["reclass_capacity_cars_per_day"]), int(r["classification_tracks"]))
        for r in _rows(folder / "nodes.csv")
    }
    arcs: list[Arc] = []
    for r in _rows(folder / "arcs.csv"):
        length, cap = float(r["length_km"]), float(r["line_capacity_trains_per_day"])
        arcs.append(Arc(r["from"], r["to"], length, cap))
        arcs.append(Arc(r["to"], r["from"], length, cap))
    demands = [
        Demand(r["id"], r["origin"], r["destination"], r["category"], float(r["cars_per_day"]), float(r["revenue_per_car"]))
        for r in _rows(folder / "demands.csv")
    ]
    classes = {
        r["id"]: ServiceClass(r["id"], float(r["speed_kmh"]), int(r["max_cars"]), float(r["train_cost_per_km"]))
        for r in _rows(folder / "service_classes.csv")
    }
    params = json.loads((folder / "params.json").read_text(encoding="utf-8"))
    inst = Instance(folder.name, yards, arcs, demands, classes, params)
    _validate(inst)
    return inst


def _validate(inst: Instance) -> None:
    for a in inst.arcs:
        if a.tail not in inst.yards or a.head not in inst.yards:
            raise ValueError(f"arc {a.tail}-{a.head} uses an unknown yard")
        if a.length_km <= 0:
            raise ValueError(f"arc {a.tail}-{a.head} has non-positive length")
    dist = inst.shortest_distances()
    ids = [d.id for d in inst.demands]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate demand ids")
    for d in inst.demands:
        if d.origin not in inst.yards or d.destination not in inst.yards:
            raise ValueError(f"demand {d.id} uses an unknown yard")
        if d.origin == d.destination:
            raise ValueError(f"demand {d.id} has identical origin and destination")
        if d.category not in CATEGORIES:
            raise ValueError(f"demand {d.id}: category must be one of {CATEGORIES}")
        if d.cars <= 0:
            raise ValueError(f"demand {d.id} has non-positive volume")
        if (d.origin, d.destination) not in dist:
            raise ValueError(f"demand {d.id}: no rail path from {d.origin} to {d.destination}")
