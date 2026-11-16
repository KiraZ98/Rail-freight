"""Step 3: run the model and print the results.

    python main.py
"""
from pathlib import Path

from model import POLICIES, solve
from read_data import read_data

# ---- settings ----
FOLDER = Path(__file__).parent / "data" / "instances" / "xin2022_example"
EPS = 1.0  # share of demand that must be served; 1.0 = all demand, as in Xin (2022)


def print_result(data, result, policy):
    print()
    print("=== policy:", policy, "===")
    print("status:", result["status"])
    if result["status"] == "no solution":
        return
    print("total cost:   ", round(result["total_cost"], 2))
    print("  train cost: ", round(result["train_cost"], 2))
    print("  car cost:   ", round(result["car_cost"], 2))
    print("revenue:      ", round(result["revenue"], 2))
    print("profit:       ", round(result["profit"], 2))
    print("demand served:", result["demand_served"], "of", result["total_demand"], "cars/day")

    print("trains per day:")
    for (i, j, c), number in result["trains"].items():
        print("  ", i, "->", j, c, ":", number)

    print("routes:")
    for k in data["demands"]:
        route = result["routes"][k]
        if route:
            text = "  ".join(i + "->" + j + " [" + c + "]" for (i, j, c) in route)
            print("  ", k, data["category"][k], ":", text, " (", round(result["travel_time"][k], 2), "h )")
        else:
            print("  ", k, data["category"][k], ": rejected")

    print("cars reclassified per station:", result["reclassified"])


if __name__ == "__main__":
    data = read_data(FOLDER)
    for policy in POLICIES:
        result = solve(data, policy=policy, eps=EPS)
        print_result(data, result, policy)
