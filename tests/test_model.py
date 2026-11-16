"""Checks of the model against the published example of Xin (2022). Run with:
    python tests/test_model.py      (or pytest)

1. The published optimum: 23,000 CNY with the services of Table 9.
2. Hand calculations with the paper's own formulas and data (time limit, eq. 4).
3. An independent recomputation of the cost from the reported routes and trains.
4. Policy ordering, eps-constraint and yard capacity mechanics.
"""
import math
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from snd import load_instance, solve  # noqa: E402
from snd.model import POLICIES  # noqa: E402

XIN2022 = Path(__file__).resolve().parents[1] / "data" / "instances" / "xin2022_example"


def test_reproduces_xin2022_published_optimum():
    # Xin (2022), illustration example: optimal objective 23,000 CNY, Table 9 services
    sol = solve(load_instance(XIN2022), policy="mixed", eps=1.0)
    assert sol.status == "optimal"
    assert abs(sol.total_cost - 23000) < 1e-6, sol.total_cost
    assert sol.frequencies == {("1", "2", "C5"): 4, ("1", "4", "C5"): 1, ("1", "5", "C2"): 1}
    assert all(len(r) == 1 for r in sol.routes.values())  # all direct, as in Table 9


def test_express_time_limit_by_hand():
    # Eq. (4): time = mileage / speed + tau^AC(origin) x train size
    # vegetable 1->5 on C2: 180 / 140 + 0.08 x 30 = 3.686 h <= 4 h
    sol = solve(load_instance(XIN2022), eps=1.0)
    assert abs(sol.travel_time_h["d3"] - (180 / 140 + 0.08 * 30)) < 1e-9

    # Same shipment alone with a 6 h limit (data of Tables 4-8):
    #   C5: 175/80  + 0.08 x 50 = 6.19 h  -> too slow
    #   C4: 175/100 + 0.08 x 50 = 5.75 h  -> cost 2000 + 5 x 175 x 2.5 = 4187.5
    #   C3: 180/120 + 0.08 x 50 = 5.50 h  -> cost 2400 + 5 x 180 x 2.5 = 4650
    # every two-leg path needs two trains (>= 3200) plus >= 2062.5 car cost
    inst = load_instance(XIN2022)
    veg = next(d for d in inst.demands if d.id == "d3")
    inst = replace(inst, demands=[replace(veg, time_limit_h=6.0)])
    sol = solve(inst, eps=1.0)
    assert abs(sol.total_cost - 4187.5) < 1e-6, sol.total_cost
    assert sol.routes["d3"] == [("1", "5", "C4")]


def test_without_revenue_nothing_is_served():
    # the paper gives costs but no revenue, so the profit model only serves demand when eps forces it
    sol = solve(load_instance(XIN2022))
    assert sol.demand_served == 0 and sol.profit == 0 and not sol.frequencies


def recompute_cost(inst, sol) -> float:
    """Cost rebuilt from routes and train counts only, without the solver's expressions."""
    svc = {s.key: s for s in inst.services}
    cost, load = 0.0, {}
    for d in inst.demands:
        route = sol.routes[d.id]
        if not route:
            continue
        assert route[0][0] == d.origin and route[-1][1] == d.destination
        for n, k in enumerate(route):
            if n:
                assert route[n - 1][1] == k[0]  # services form a chain
            cost += svc[k].mileage_km * d.cars * inst.categories[d.category].car_cost_per_car_km
            load[k] = load.get(k, 0.0) + d.cars
    for k, cars in load.items():
        assert sol.frequencies[k] == math.ceil(cars / inst.service_classes[k[2]].max_cars)  # no spare trains
    for k, trains in sol.frequencies.items():
        assert k in load  # no empty services
        cost += svc[k].train_cost * trains
    return cost


def test_all_policies_consistent():
    inst = load_instance(XIN2022)
    cost = {}
    for policy in POLICIES:
        sol = solve(inst, policy=policy, eps=1.0)
        assert sol.status == "optimal"
        assert abs(recompute_cost(inst, sol) - sol.total_cost) < 1e-6
        cost[policy] = sol.total_cost
    # each policy is a relaxation of the next: inseparable <= mixed <= intree in cost
    assert cost["inseparable"] <= cost["mixed"] + 1e-6 <= cost["intree"] + 2e-6, cost


def test_yard_capacity_mechanics():
    inst = load_instance(XIN2022)
    closed = {v: 0.0 for v in inst.yards}  # no reclassification allowed anywhere
    hard = solve(inst, eps=1.0, yard_capacity=closed)
    assert all(t == 0 for t in hard.yard_throughput.values())
    assert all(len(r) == 1 for r in hard.routes.values())
    soft = solve(inst, eps=1.0, yard_capacity=closed, elastic=True)
    assert soft.total_cost <= hard.total_cost + 1e-6


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok  ", name)
