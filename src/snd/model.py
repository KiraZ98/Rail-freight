"""Simplified service network design MILP with blocking policies.

NOT yet checked against the equations of Xin, Wu & Wang (2025): it is built from the
standard train formation / blocking formulations and has to be compared with the paper.

Modelling choices
-----------------
* A service (i, j, c) is a direct train of class c from yard i to yard j that runs on the
  shortest rail path and is not reclassified on the way. One block per train.
* Every demand is accepted or rejected as a whole (binary), and an accepted demand follows
  one sequence of services. Cars are reclassified at every yard where they change service.
* Inseparable policy: each demand chooses its own service sequence.
* Intree policy: at a yard, all cars of the same category and the same destination leave on
  the same service, whatever their origin (one tree per destination and category).
* Profit = revenue - train cost - car haul cost - reclassification cost - accumulation cost
  (- penalty for flow above yard capacity if `elastic`).
  Accumulation cost is a fixed daily cost per operated service:
  accumulation_cost_per_car_hour * accumulation_parameter_hours * max_cars.
* Line capacity counts trains per day and direction on every line of the shortest path.

Role B calls `solve` inside the two-stage decomposition and the benchmark; role C calls it
for the epsilon-constraint runs and reads `Solution` for metrics and plots.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .instance import Instance

# policy -> blocking rule per demand category
POLICIES = {
    "mixed": {"express": "inseparable", "bulk": "intree"},
    "intree": {"express": "intree", "bulk": "intree"},
    "inseparable": {"express": "inseparable", "bulk": "inseparable"},
}


@dataclass
class Solution:
    status: str  # "optimal", "time_limit", "infeasible"
    profit: float
    demand_served: float  # cars per day actually transported
    total_demand: float
    runtime_s: float
    mip_gap: float
    # (origin yard, destination yard, service class) -> trains per day
    frequencies: dict[tuple[str, str, str], int] = field(default_factory=dict)
    # demand id -> cars per day served (0 if rejected)
    served: dict[str, float] = field(default_factory=dict)
    # demand id -> services used in order, as (from yard, to yard, class); empty if rejected
    routes: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)
    # demand id -> yards where the cars are reclassified (origin and destination excluded)
    reclass_yards: dict[str, list[str]] = field(default_factory=dict)
    # yard id -> cars reclassified per day
    yard_throughput: dict[str, float] = field(default_factory=dict)
    # revenue and the individual cost terms
    breakdown: dict[str, float] = field(default_factory=dict)

    @property
    def service_level(self) -> float:
        return self.demand_served / self.total_demand if self.total_demand else 0.0


def shortest_path_arcs(instance: Instance, dist: dict) -> dict[tuple[str, str], list[tuple[str, str]]]:
    """Directed lines on the shortest path for every ordered yard pair."""
    length = {(a.tail, a.head): a.length_km for a in instance.arcs}
    paths = {}
    for (i, j) in dist:
        cur, arcs = i, []
        while cur != j:
            nxt = next(
                v for (t, v), km in length.items()
                if t == cur and abs(km + (dist[v, j] if v != j else 0.0) - dist[cur, j]) < 1e-6
            )
            arcs.append((cur, nxt))
            cur = nxt
        paths[i, j] = arcs
    return paths


def solve(
    instance: Instance,
    policy: str = "mixed",
    yard_capacity: dict[str, float] | None = None,
    elastic: bool = False,
    eps: float | None = None,
    time_limit: float = 3600.0,
    verbose: bool = False,
) -> Solution:
    """Solve the service network design model.

    policy         "mixed" (express inseparable, bulk intree), "intree" or "inseparable"
                   (the same rule for both categories).
    yard_capacity  yard id -> reclassification limit in cars per day. None = no limit
                   (the 100 % scenario). For 80 % / 60 %, pass that share of the
                   `yard_throughput` of the reference run.
    elastic        False = hard limit; True = flow above the limit is penalised with
                   params["over_capacity_penalty_per_car"].
    eps            if given, adds DemandServed >= eps * TotalDemand (RQ3).
    time_limit     Gurobi time limit in seconds.
    """
    if policy not in POLICIES:
        raise ValueError(f"policy must be one of {tuple(POLICIES)}")
    import gurobipy as gp
    from gurobipy import GRB

    rule = POLICIES[policy]
    P = instance.params
    classes = instance.service_classes
    demands = instance.demands
    allowed = P.get("allowed_classes", {"express": ["express"], "bulk": list(classes)})
    dist = instance.shortest_distances()
    paths = shortest_path_arcs(instance, dist)
    services = [(i, j, c) for (i, j) in dist for c in classes]
    total = instance.total_demand
    acc_unit = P["accumulation_cost_per_car_hour"] * P["accumulation_parameter_hours"]

    m = gp.Model("snd")
    m.Params.OutputFlag = int(verbose)
    m.Params.TimeLimit = time_limit

    y = m.addVars(services, vtype=GRB.INTEGER, name="trains")
    u = m.addVars(services, vtype=GRB.BINARY, name="operated")
    s = m.addVars([d.id for d in demands], vtype=GRB.BINARY, name="accept")
    # w[k, i, j, c] = 1 if demand k travels on service (i, j, c)
    w = {
        (d.id, i, j, c): m.addVar(vtype=GRB.BINARY, name=f"use[{d.id},{i},{j},{c}]")
        for d in demands
        for (i, j, c) in services
        if c in allowed[d.category] and j != d.origin and i != d.destination
    }

    # each accepted demand follows one chain of services from origin to destination
    for d in demands:
        for v in instance.yards:
            out = gp.quicksum(w[d.id, i, j, c] for (i, j, c) in services if i == v and (d.id, i, j, c) in w)
            inn = gp.quicksum(w[d.id, i, j, c] for (i, j, c) in services if j == v and (d.id, i, j, c) in w)
            if v == d.origin:
                m.addConstr(out == s[d.id])
            elif v == d.destination:
                m.addConstr(inn == s[d.id])
            else:
                m.addConstr(out == inn)
                m.addConstr(out <= 1)

    # train capacity, and a service is "operated" if it runs at least once
    for (i, j, c) in services:
        load = gp.quicksum(d.cars * w[d.id, i, j, c] for d in demands if (d.id, i, j, c) in w)
        m.addConstr(load <= classes[c].max_cars * y[i, j, c])
        m.addConstr(y[i, j, c] <= math.ceil(total / classes[c].max_cars) * u[i, j, c])

    # line capacity per direction
    for a in instance.arcs:
        on_line = [sv for sv in services if (a.tail, a.head) in paths[sv[0], sv[1]]]
        m.addConstr(gp.quicksum(y[sv] for sv in on_line) <= a.capacity)

    # intree rule: one outgoing service per (yard, destination, category)
    x = {}
    for d in demands:
        if rule[d.category] != "intree":
            continue
        for (i, j, c) in services:
            if (d.id, i, j, c) not in w:
                continue
            key = (d.category, d.destination, i, j, c)
            if key not in x:
                x[key] = m.addVar(vtype=GRB.BINARY, name=f"tree[{','.join(key)}]")
            m.addConstr(w[d.id, i, j, c] <= x[key])
    for cat, dest, i in {(k[0], k[1], k[2]) for k in x}:
        m.addConstr(gp.quicksum(v for k, v in x.items() if k[:3] == (cat, dest, i)) <= 1)

    # cars reclassified per yard = cars arriving at a yard that is not their destination
    throughput = {
        v: gp.quicksum(
            d.cars * w[d.id, i, j, c]
            for d in demands if d.destination != v
            for (i, j, c) in services if j == v and (d.id, i, j, c) in w
        )
        for v in instance.yards
    }
    over = {}
    if yard_capacity is not None:
        for v, cap in yard_capacity.items():
            if elastic:
                over[v] = m.addVar(lb=0.0, name=f"over[{v}]")
                m.addConstr(throughput[v] <= cap + over[v])
            else:
                m.addConstr(throughput[v] <= cap)

    served_cars = gp.quicksum(d.cars * s[d.id] for d in demands)
    if eps is not None:
        m.addConstr(served_cars >= eps * total)

    terms = {
        "revenue": gp.quicksum(d.cars * d.revenue_per_car * s[d.id] for d in demands),
        "train_cost": gp.quicksum(classes[c].train_cost_per_km * dist[i, j] * y[i, j, c] for (i, j, c) in services),
        "car_haul_cost": gp.quicksum(
            P["car_cost_per_km"] * dist[i, j] * d.cars * w[d.id, i, j, c]
            for d in demands for (i, j, c) in services if (d.id, i, j, c) in w
        ),
        "reclass_cost": P["reclass_cost_per_car"] * gp.quicksum(throughput.values()),
        "accumulation_cost": gp.quicksum(acc_unit * classes[c].max_cars * u[i, j, c] for (i, j, c) in services),
        "over_capacity_penalty": P["over_capacity_penalty_per_car"] * gp.quicksum(over.values()),
    }
    m.setObjective(terms["revenue"] - gp.quicksum(v for k, v in terms.items() if k != "revenue"), GRB.MAXIMIZE)
    m.optimize()

    if m.SolCount == 0:
        return Solution("infeasible", 0.0, 0.0, total, m.Runtime, float("inf"))

    routes, reclass = {}, {}
    for d in demands:
        route, cur = [], d.origin
        if s[d.id].X > 0.5:
            while cur != d.destination:
                step = next((i, j, c) for (i, j, c) in services if i == cur and (d.id, i, j, c) in w and w[d.id, i, j, c].X > 0.5)
                route.append(step)
                cur = step[1]
        routes[d.id] = route
        reclass[d.id] = [j for (_, j, _) in route[:-1]]

    def val(expr) -> float:
        return expr.getValue() if hasattr(expr, "getValue") else float(expr)

    return Solution(
        status="optimal" if m.Status == GRB.OPTIMAL else "time_limit",
        profit=m.ObjVal,
        demand_served=sum(d.cars for d in demands if s[d.id].X > 0.5),
        total_demand=total,
        runtime_s=m.Runtime,
        mip_gap=m.MIPGap,
        frequencies={sv: round(y[sv].X) for sv in services if y[sv].X > 0.5},
        served={d.id: d.cars if s[d.id].X > 0.5 else 0.0 for d in demands},
        routes=routes,
        reclass_yards=reclass,
        yard_throughput={v: val(e) for v, e in throughput.items()},
        breakdown={k: val(v) for k, v in terms.items()},
    )
