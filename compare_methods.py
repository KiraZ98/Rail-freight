"""Compare the three methods of RQ2 on one instance.

    python compare_methods.py
"""
from read_data import read_data
from model import solve
from two_stage import solve_two_stage

FOLDER = "data/instances/xin2025_example"

data = read_data(FOLDER)

a = solve(data)                                          # A: integrated model [OM], exact
b = solve_two_stage(data)                                # B: decomposition, both stages exact
c = solve_two_stage(data, second_stage="greedy")         # C: stage 1 exact, stage 2 greedy

for name, r in [("A", a), ("B", b), ("C", c)]:
    print(name, round(r["profit"], 2), len(r["accepted"]), round(r["runtime"], 3), "s", r["status"])