"""Service network design MILP with blocking policies.

Built on the integer model of Xin (2022), PLOS ONE 17(12): e0276671, equations (1)-(8):

* (1) cost = train cost per train x frequency + car cost per car-km x mileage x cars
* (2) flow balance: each shipment follows one chain of train services
* (3) nonseparable shipments: one service per leg, the whole volume together
* (4) transportation time limit for express goods: running time + accumulation time at the
      origin (tau^AC x train size) + transfer time at each intermediate station (tau^TF x train size)
* (5) tree-shaped paths for non-express goods; implemented here as the intree rule (all
      non-express cars at a yard with the same destination leave on the same service), the
      blocking-policy form used by Xin, Wu & Wang (2025)
* (6) train capacity: cars on a service <= train size x frequency

Extensions, all optional, switched off when their data are not given:

* revenue and demand rejection (profit objective of Xin, Wu & Wang 2025), with
  eps-constraint DemandServed >= eps x TotalDemand (Miettinen 1998); eps = 1 gives the
  cost-minimising model of Xin (2022) where all demand must be served
* yard reclassification capacity, hard or elastic (Lin et al. 2021)
* line capacity, when services are generated on known paths
* reclassification and accumulation cost (params.json), 0 when not given

NOT yet checked against the equations of Xin, Wu & Wang (2025), which is not available yet.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .instance import Instance

# policy -> blocking rule for express and non-express goods
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
    # demand id -> transportation time in hours by constraint (4) of Xin (2022)
    travel_time_h: dict[str, float] = field(default_factory=dict)
    # revenue and the individual cost terms
    breakdown: dict[str, float] = field(default_factory=dict)

    @property
    def service_level(self) -> float:
        return self.demand_served / self.total_demand if self.total_demand else 0.0

    @property
    def total_cost(self) -> float:
        return sum(v for k, v in self.breakdown.items() if k != "revenue")


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

    policy         "mixed" (express inseparable, non-express intree), "intree" or
                   "inseparable" (the same rule for all goods).
    yard_capacity  yard id -> reclassification limit in cars per day. None = the
                   capacities in nodes.csv where given, otherwise no limit.
    elastic        False = hard limit; True = flow above the limit is penalised with
                   params["over_capacity_penalty_per_car"] (Lin et al. 2021 use 1500).
    eps            if given, adds DemandServed >= eps * TotalDemand. eps = 1 serves all
                   demand, as in Xin (2022).
    time_limit     Gurobi time limit in seconds.
    """
    if policy not in POLICIES:
        raise ValueError(f"policy must be one of {tuple(POLICIES)}")
    import gurobipy as gp
    from gurobipy import GRB

    rule = POLICIES[policy]
    P = instance.params
    yards = instance.yards
    classes = instance.service_classes
    demands = instance.demands
    svc = {s.key: s for s in instance.services}
    S = list(svc)
    total = instance.total_demand
    group = {d.id: "express" if instance.is_express(d) else "bulk" for d in demands}
    if yard_capacity is None:
        yard_capacity = {v: y.reclass_capacity for v, y in yards.items() if y.reclass_capacity is not None}

    m = gp.Model("snd")
    m.Params.OutputFlag = int(verbose)
    m.Params.TimeLimit = time_limit

    y = m.addVars(S, vtype=GRB.INTEGER, lb=0, name="trains")  # (8)
    s = m.addVars([d.id for d in demands], vtype=GRB.BINARY, name="accept")
    # (7) x[k, i, j, c] = 1 if demand k is assigned to service (i, j, c)
    x = {
        (d.id, *k): m.addVar(vtype=GRB.BINARY, name=f"x[{d.id},{','.join(k)}]")
        for d in demands for k in S
        if k[1] != d.origin and k[0] != d.destination
    }
    out_of = {(d.id, v): [] for d in demands for v in yards}
    into = {(d.id, v): [] for d in demands for v in yards}
    for (kid, i, j, c), var in x.items():
        out_of[kid, i].append(var)
        into[kid, j].append(var)

    # (2) flow balance, (3) one service per leg; an accepted shipment leaves every yard at most once
    for d in demands:
        for v in yards:
            out, inn = gp.quicksum(out_of[d.id, v]), gp.quicksum(into[d.id, v])
            if v == d.origin:
                m.addConstr(out == s[d.id])
            elif v == d.destination:
                m.addConstr(inn == s[d.id])
            else:
                m.addConstr(out == inn)
                m.addConstr(out <= 1)

    # (4) transportation time limit for express goods
    def time_expr(d):
        return gp.quicksum(
            var * (svc[i, j, c].mileage_km / classes[c].speed_kmh
                   + (yards[i].accumulation_time_h if i == d.origin else yards[i].transfer_time_h) * classes[c].max_cars)
            for (kid, i, j, c), var in x.items() if kid == d.id
        )
    times = {d.id: time_expr(d) for d in demands}
    for d in demands:
        if d.time_limit_h is not None and instance.is_express(d):
            m.addConstr(times[d.id] <= d.time_limit_h, name=f"time[{d.id}]")

    # (6) train capacity
    load = {k: gp.LinExpr() for k in S}
    for (kid, i, j, c), var in x.items():
        load[i, j, c] += next(d.cars for d in demands if d.id == kid) * var
    for k in S:
        m.addConstr(load[k] <= classes[k[2]].max_cars * y[k])

    # line capacity, only for services whose path is known
    for a in instance.arcs:
        if a.capacity is None:
            continue
        on_line = [k for k in S if svc[k].path and (a.tail, a.head) in svc[k].path]
        if on_line:
            m.addConstr(gp.quicksum(y[k] for k in on_line) <= a.capacity)

    # (5) blocking rule: intree = one outgoing service per (yard, destination, goods group)
    tree = {}
    for (kid, i, j, c), var in x.items():
        d = next(d for d in demands if d.id == kid)
        if rule[group[kid]] != "intree":
            continue
        key = (group[kid], d.destination, i, j, c)
        if key not in tree:
            tree[key] = m.addVar(vtype=GRB.BINARY, name=f"tree[{','.join(key)}]")
        m.addConstr(var <= tree[key])
    for g, dest, i in {k[:3] for k in tree}:
        m.addConstr(gp.quicksum(v for k, v in tree.items() if k[:3] == (g, dest, i)) <= 1)

    # cars reclassified per yard = cars arriving at a yard that is not their destination
    cars = {d.id: d.cars for d in demands}
    dest = {d.id: d.destination for d in demands}
    throughput = {v: gp.LinExpr() for v in yards}
    for (kid, i, j, c), var in x.items():
        if j != dest[kid]:
            throughput[j] += cars[kid] * var
    over = {}
    for v, cap in yard_capacity.items():
        if elastic:
            over[v] = m.addVar(lb=0.0, name=f"over[{v}]")
            m.addConstr(throughput[v] <= cap + over[v])
        else:
            m.addConstr(throughput[v] <= cap)

    if eps is not None:
        m.addConstr(gp.quicksum(d.cars * s[d.id] for d in demands) >= eps * total - 1e-6)

    acc_unit = P.get("accumulation_cost_per_car_hour", 0.0) * P.get("accumulation_parameter_hours", 0.0)
    u = {}
    if acc_unit:
        u = m.addVars(S, vtype=GRB.BINARY, name="operated")
        for k in S:
            m.addConstr(y[k] <= math.ceil(total / classes[k[2]].max_cars) * u[k])
    car_cost = {d.id: instance.categories[d.category].car_cost_per_car_km for d in demands}
    terms = {
        "revenue": gp.quicksum(d.cars * d.revenue_per_car * s[d.id] for d in demands),
        "train_cost": gp.quicksum(svc[k].train_cost * y[k] for k in S),
        "car_cost": gp.quicksum(
            svc[i, j, c].mileage_km * cars[kid] * car_cost[kid] * var for (kid, i, j, c), var in x.items()
        ),
        "reclass_cost": P.get("reclass_cost_per_car", 0.0) * gp.quicksum(throughput.values()),
        "accumulation_cost": gp.quicksum(acc_unit * classes[k[2]].max_cars * u[k] for k in u),
        "over_capacity_penalty": P.get("over_capacity_penalty_per_car", 0.0) * gp.quicksum(over.values()),
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
                step = next(k for k in S if k[0] == cur and (d.id, *k) in x and x[d.id, *k].X > 0.5)
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
        frequencies={k: round(y[k].X) for k in S if y[k].X > 0.5},
        served={d.id: d.cars if s[d.id].X > 0.5 else 0.0 for d in demands},
        routes=routes,
        reclass_yards=reclass,
        yard_throughput={v: val(e) for v, e in throughput.items()},
        travel_time_h={d.id: val(times[d.id]) for d in demands if routes[d.id]},
        breakdown={k: val(v) for k, v in terms.items()},
    )
