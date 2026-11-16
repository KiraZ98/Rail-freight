"""Instance format: one folder per network instance. Every value must come from a cited
source; the folder's SOURCES.md says which table or document each file comes from.

    nodes.csv            id, name, reclass_capacity_cars_per_day, classification_tracks,
                         accumulation_time_h, transfer_time_h          (blank = not given)
    categories.csv       id, express (yes|no), car_cost_per_car_km
    demands.csv          id, origin, destination, category, cars_per_day,
                         revenue_per_car, time_limit_h                 (blank = not given)
    service_classes.csv  id, speed_kmh, max_cars [, train_cost_per_km]
    services.csv         origin, destination, class, mileage_km, train_cost   (cost per train)
    arcs.csv             from, to, length_km, line_capacity_trains_per_day    (undirected)
    params.json          optional scalar parameters

Candidate services come from services.csv when it exists (as in Xin 2022, Table 8).
Without it they are generated on the shortest rail path from arcs.csv, which then needs
train_cost_per_km in service_classes.csv.

Only the standard library is used here, so loading works without Gurobi or pandas.
"""
from __future__ import annotations

import csv
import heapq
import json
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class Yard:
    id: str
    name: str
    reclass_capacity: float | None  # cars per day
    tracks: int | None  # classification tracks
    accumulation_time_h: float  # Xin (2022) tau^AC, hours per car of train size
    transfer_time_h: float  # Xin (2022) tau^TF, hours per car of train size


@dataclass(frozen=True)
class Arc:
    tail: str
    head: str
    length_km: float
    capacity: float | None  # trains per day


@dataclass(frozen=True)
class Category:
    id: str
    express: bool
    car_cost_per_car_km: float


@dataclass(frozen=True)
class Demand:
    id: str
    origin: str
    destination: str
    category: str
    cars: float  # cars per day
    revenue_per_car: float
    time_limit_h: float | None


@dataclass(frozen=True)
class ServiceClass:
    id: str
    speed_kmh: float
    max_cars: int
    train_cost_per_km: float | None


@dataclass(frozen=True)
class Service:
    origin: str
    destination: str
    cls: str
    mileage_km: float
    train_cost: float  # per train
    path: tuple[tuple[str, str], ...] | None = None  # directed lines used, if known

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.origin, self.destination, self.cls)


@dataclass
class Instance:
    name: str
    yards: dict[str, Yard]
    arcs: list[Arc]  # directed: every row of arcs.csv appears in both directions
    categories: dict[str, Category]
    demands: list[Demand]
    service_classes: dict[str, ServiceClass]
    services: list[Service]
    params: dict

    @property
    def total_demand(self) -> float:
        return sum(d.cars for d in self.demands)

    def is_express(self, d: Demand) -> bool:
        return self.categories[d.category].express

    def scaled(self, demand_factor: float = 1.0) -> "Instance":
        """Copy with all demand volumes multiplied (base, +25 %, +50 % scenarios)."""
        demands = [replace(d, cars=d.cars * demand_factor) for d in self.demands]
        return replace(self, demands=demands)


def shortest_paths(yards, arcs) -> dict[tuple[str, str], tuple[float, tuple]]:
    """(km, directed lines) of the shortest rail path between every ordered pair of yards."""
    adj: dict[str, list[tuple[str, float]]] = {y: [] for y in yards}
    for a in arcs:
        adj[a.tail].append((a.head, a.length_km))
    result = {}
    for src in yards:
        best, prev = {src: 0.0}, {}
        heap = [(0.0, src)]
        while heap:
            d, u = heapq.heappop(heap)
            if d > best[u]:
                continue
            for v, w in adj[u]:
                if d + w < best.get(v, float("inf")):
                    best[v], prev[v] = d + w, u
                    heapq.heappush(heap, (d + w, v))
        for dst, km in best.items():
            if dst == src:
                continue
            path, cur = [], dst
            while cur != src:
                path.append((prev[cur], cur))
                cur = prev[cur]
            result[src, dst] = (km, tuple(reversed(path)))
    return result


def _rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _num(value: str | None, cast=float):
    return None if value is None or value.strip() == "" else cast(value)


def load_instance(folder: str | Path) -> Instance:
    folder = Path(folder)
    yards = {
        r["id"]: Yard(
            r["id"], r["name"],
            _num(r.get("reclass_capacity_cars_per_day")),
            _num(r.get("classification_tracks"), int),
            _num(r.get("accumulation_time_h")) or 0.0,
            _num(r.get("transfer_time_h")) or 0.0,
        )
        for r in _rows(folder / "nodes.csv")
    }
    arcs: list[Arc] = []
    if (folder / "arcs.csv").exists():
        for r in _rows(folder / "arcs.csv"):
            length, cap = float(r["length_km"]), _num(r.get("line_capacity_trains_per_day"))
            arcs += [Arc(r["from"], r["to"], length, cap), Arc(r["to"], r["from"], length, cap)]
    categories = {
        r["id"]: Category(r["id"], r["express"].strip().lower() == "yes", float(r["car_cost_per_car_km"]))
        for r in _rows(folder / "categories.csv")
    }
    demands = [
        Demand(r["id"], r["origin"], r["destination"], r["category"], float(r["cars_per_day"]),
               _num(r.get("revenue_per_car")) or 0.0, _num(r.get("time_limit_h")))
        for r in _rows(folder / "demands.csv")
    ]
    classes = {
        r["id"]: ServiceClass(r["id"], float(r["speed_kmh"]), int(r["max_cars"]), _num(r.get("train_cost_per_km")))
        for r in _rows(folder / "service_classes.csv")
    }
    if (folder / "services.csv").exists():
        services = [
            Service(r["origin"], r["destination"], r["class"], float(r["mileage_km"]), float(r["train_cost"]))
            for r in _rows(folder / "services.csv")
        ]
    else:
        services = []
        for (i, j), (km, path) in shortest_paths(yards, arcs).items():
            for c in classes.values():
                if c.train_cost_per_km is None:
                    raise ValueError(f"no services.csv and no train_cost_per_km for class {c.id}")
                services.append(Service(i, j, c.id, km, c.train_cost_per_km * km, path))
    params_file = folder / "params.json"
    params = json.loads(params_file.read_text(encoding="utf-8")) if params_file.exists() else {}
    inst = Instance(folder.name, yards, arcs, categories, demands, classes, services, params)
    _validate(inst)
    return inst


def _validate(inst: Instance) -> None:
    for a in inst.arcs:
        if a.tail not in inst.yards or a.head not in inst.yards:
            raise ValueError(f"arc {a.tail}-{a.head} uses an unknown yard")
    keys = [s.key for s in inst.services]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate (origin, destination, class) in services")
    for s in inst.services:
        if s.origin not in inst.yards or s.destination not in inst.yards or s.origin == s.destination:
            raise ValueError(f"service {s.key} has an invalid origin or destination")
        if s.cls not in inst.service_classes:
            raise ValueError(f"service {s.key} uses an unknown class")
    ids = [d.id for d in inst.demands]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate demand ids")
    for d in inst.demands:
        if d.origin not in inst.yards or d.destination not in inst.yards or d.origin == d.destination:
            raise ValueError(f"demand {d.id} has an invalid origin or destination")
        if d.category not in inst.categories:
            raise ValueError(f"demand {d.id} uses unknown category {d.category}")
        if d.cars <= 0:
            raise ValueError(f"demand {d.id} has non-positive volume")
