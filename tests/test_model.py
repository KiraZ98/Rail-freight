"""Checks of the base model. Run with:  python tests/test_model.py   (or pytest)

1. Two one-demand cases whose optimum is computed by hand in the comments.
2. An independent recomputation of the profit from the reported routes and trains.
3. Policy ordering: inseparable >= mixed >= intree (each is a relaxation of the next).
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from snd import load_instance, solve  # noqa: E402
from snd.instance import Demand, Instance  # noqa: E402
from snd.model import POLICIES  # noqa: E402

TOY = Path(__file__).resolve().parents[1] / "data" / "instances" / "toy6"


def only(inst: Instance, demand: Demand) -> Instance:
    return Instance(inst.name, inst.yards, inst.arcs, [demand], inst.service_classes, inst.params)


def test_single_bulk_demand_by_hand():
    # 20 bulk cars C->D, 120 km, revenue 180/car           -> revenue           3600
    # one ordinary train (50 cars): 8.0 * 120              -> train cost         960
    # car haul: 0.5 * 120 * 20                             -> haul cost         1200
    # accumulation: 1.0 * 10 h * 50 cars                   -> accumulation       500
    # profit = 3600 - 960 - 1200 - 500 = 940
    # (fast train: 1200 + 1200 + 300 = 2700 > 2660, express: 1440 + 1200 + 200 = 2840)
    inst = only(load_instance(TOY), Demand("k", "C", "D", "bulk", 20, 180))
    for policy in POLICIES:
        sol = solve(inst, policy=policy)
        assert abs(sol.profit - 940) < 1e-6, sol.profit
        assert sol.frequencies == {("C", "D", "ordinary"): 1}


def test_single_express_demand_by_hand():
    # 10 express cars C->F, 360 km, revenue 1080/car       -> revenue          10800
    # one express train: 12.0 * 360                        -> train cost        4320
    # car haul: 0.5 * 360 * 10                             -> haul cost         1800
    # accumulation: 1.0 * 10 h * 20 cars                   -> accumulation       200
    # profit = 10800 - 4320 - 1800 - 200 = 4480   (going via E adds 200 + 300 reclassification)
    inst = only(load_instance(TOY), Demand("k", "C", "F", "express", 10, 1080))
    sol = solve(inst, policy="mixed")
    assert abs(sol.profit - 4480) < 1e-6, sol.profit
    assert sol.routes["k"] == [("C", "F", "express")]


def test_unprofitable_demand_is_rejected():
    # 3 bulk cars C->D earn 540 but the cheapest train alone costs 960
    inst = only(load_instance(TOY), Demand("k", "C", "D", "bulk", 3, 180))
    sol = solve(inst)
    assert sol.profit == 0 and sol.demand_served == 0 and not sol.frequencies


def recompute_profit(inst: Instance, sol) -> float:
    """Profit rebuilt from routes and train counts only, without the solver's expressions."""
    P, dist, cls = inst.params, inst.shortest_distances(), inst.service_classes
    profit, load = 0.0, {}
    for d in inst.demands:
        route = sol.routes[d.id]
        if not route:
            continue
        assert route[0][0] == d.origin and route[-1][1] == d.destination
        profit += d.cars * d.revenue_per_car
        for n, (i, j, c) in enumerate(route):
            if n:
                assert route[n - 1][1] == i  # services form a chain
            profit -= P["car_cost_per_km"] * dist[i, j] * d.cars
            load[i, j, c] = load.get((i, j, c), 0.0) + d.cars
        profit -= P["reclass_cost_per_car"] * d.cars * (len(route) - 1)
    for (i, j, c), cars in load.items():
        assert sol.frequencies[i, j, c] == math.ceil(cars / cls[c].max_cars)  # no spare trains
    for (i, j, c), trains in sol.frequencies.items():
        assert (i, j, c) in load  # no empty services
        profit -= cls[c].train_cost_per_km * dist[i, j] * trains
        profit -= P["accumulation_cost_per_car_hour"] * P["accumulation_parameter_hours"] * cls[c].max_cars
    return profit


def check_intree(inst: Instance, sol, categories) -> None:
    nxt = {}
    for d in inst.demands:
        if d.category in categories:
            for step in sol.routes[d.id]:
                key = (d.category, d.destination, step[0])
                assert nxt.setdefault(key, step) == step, f"intree rule violated at {key}"


def test_toy_all_policies():
    inst = load_instance(TOY)
    ref = solve(inst, policy="mixed")
    for cap in (None, {v: 0.8 * t for v, t in ref.yard_throughput.items()}):
        profit = {}
        for policy, rule in POLICIES.items():
            sol = solve(inst, policy=policy, yard_capacity=cap)
            assert sol.status == "optimal"
            assert abs(recompute_profit(inst, sol) - sol.profit) < 1e-4
            check_intree(inst, sol, [c for c, r in rule.items() if r == "intree"])
            if cap:
                assert all(sol.yard_throughput[v] <= cap[v] + 1e-6 for v in cap)
            profit[policy] = sol.profit
        assert profit["inseparable"] >= profit["mixed"] - 1 >= profit["intree"] - 2, profit


def test_eps_constraint_and_elastic():
    inst = load_instance(TOY)
    base = solve(inst)
    forced = solve(inst, eps=1.0)
    assert forced.service_level == 1.0 and forced.profit <= base.profit + 1e-6
    tight = {v: 0.0 for v in inst.yards}
    hard = solve(inst, yard_capacity=tight)
    soft = solve(inst, yard_capacity=tight, elastic=True)
    assert all(t == 0 for t in hard.yard_throughput.values())
    assert base.profit + 1e-6 >= soft.profit >= hard.profit - 1e-6


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok  ", name)
