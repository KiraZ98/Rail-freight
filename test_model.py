"""Check the model against the published example of Xin (2022).

    python test_model.py
"""
import copy
from pathlib import Path

from model import POLICIES, solve
from read_data import read_data

FOLDER = Path(__file__).parent / "data" / "instances" / "xin2022_example"


def test_published_optimum():
    # Xin (2022), illustration example: optimal cost 23,000 CNY with the services of Table 9
    data = read_data(FOLDER)
    result = solve(data, policy="mixed", eps=1.0)
    assert result["status"] == "optimal"
    assert abs(result["total_cost"] - 23000) < 0.001
    assert result["trains"] == {("1", "2", "C5"): 4, ("1", "4", "C5"): 1, ("1", "5", "C2"): 1}


def test_time_limit_by_hand():
    # Equation (4): time = mileage / speed + accumulation time at the origin x train size
    # vegetables 1->5 on a C2 train: 180 / 140 + 0.08 x 30 = 3.69 h, within the 4 h limit
    data = read_data(FOLDER)
    result = solve(data, eps=1.0)
    assert abs(result["travel_time"]["d3"] - (180 / 140 + 0.08 * 30)) < 0.001

    # Only the vegetables, with a 6 h limit instead of 4 h (data of Tables 4-8):
    #   C5: 175 / 80  + 0.08 x 50 = 6.19 h  -> too slow
    #   C4: 175 / 100 + 0.08 x 50 = 5.75 h  -> cost 2000 + 5 x 175 x 2.5 = 4187.5  (cheapest)
    #   C3: 180 / 120 + 0.08 x 50 = 5.50 h  -> cost 2400 + 5 x 180 x 2.5 = 4650
    data = copy.deepcopy(data)
    data["demands"] = ["d3"]
    data["time_limit"]["d3"] = 6.0
    result = solve(data, eps=1.0)
    assert abs(result["total_cost"] - 4187.5) < 0.001
    assert result["routes"]["d3"] == [("1", "5", "C4")]


def test_cost_adds_up():
    # Recompute the cost from the routes and trains, without using the solver's own numbers
    data = read_data(FOLDER)
    for policy in POLICIES:
        result = solve(data, policy=policy, eps=1.0)
        cost = 0
        for service, number in result["trains"].items():
            cost += data["train_cost"][service] * number
        for k in data["demands"]:
            for service in result["routes"][k]:
                cost += data["car_cost"][data["category"][k]] * data["mileage"][service] * data["volume"][k]
        assert abs(cost - result["total_cost"]) < 0.001


def test_no_revenue_no_service():
    # The paper gives no revenue, so without eps the profit model serves nothing
    data = read_data(FOLDER)
    result = solve(data)
    assert result["demand_served"] == 0
    assert result["trains"] == {}


def test_yard_capacity():
    # With zero capacity everywhere no car may be reclassified, so every route is direct
    data = read_data(FOLDER)
    closed = {v: 0 for v in data["stations"]}
    hard = solve(data, eps=1.0, yard_capacity=closed)
    assert all(cars == 0 for cars in hard["reclassified"].values())
    assert all(len(route) == 1 for route in hard["routes"].values())
    # an elastic limit can never be more expensive than a hard one
    elastic = solve(data, eps=1.0, yard_capacity=closed, penalty=1500)
    assert elastic["total_cost"] <= hard["total_cost"] + 0.001


if __name__ == "__main__":
    test_published_optimum()
    test_time_limit_by_hand()
    test_cost_adds_up()
    test_no_revenue_no_service()
    test_yard_capacity()
    print("All tests passed.")
