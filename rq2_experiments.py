"""RQ2: How do the computational performance and solution quality of a two-stage decomposition
heuristic compare against an exact solver (Gurobi) as the network scales?

    python rq2_experiments.py

The script takes every random network that generate_instance.py has made in data/instances
(recipe of Section 6.1.1 of the base paper; sizes and seeds are set there, so run it first) and
solves it with three methods:

    A  exact: integrated model [OM], Gurobi                      model.solve
    B  two-stage decomposition, both stages Gurobi               solve_two_stage(...)
    C  two-stage heuristic: stage 1 Gurobi, stage 2 greedy       solve_two_stage(..., second_stage="greedy")
       (Algorithm 2 of the base paper, greedy.py)

Memory: A and B are skipped on networks above MAX_EXACT_X x variables. A file gurobi.env in this
folder can limit Gurobi further (for example "Threads 2", "NodefileStart 0.5", "SoftMemLimit 4").

Output in results/ (every table is also printed):
    rq2_runs.csv                  one row per network and method
    rq2_runtime_s.csv             mean runtime per size and method
    rq2_finished.csv              runs that finished normally
    rq2_gap_mean_pct.csv          mean profit gap of B and C to A
    rq2_gap_max_pct.csv           largest profit gap of B and C to A
    rq2_speedup.csv               speed-up of B and C against A
    rq2_greedy_loss_pct.csv       profit lost by the greedy stage 2 alone (C against B)
    rq2_exact_vs_heuristic.csv    exact (A) against heuristic (C), side by side; also as .png
    rq2_runtime.png, rq2_profit_gap.png, rq2_speedup.png
"""
import re
import time
from pathlib import Path

import gurobipy as gp
import matplotlib.pyplot as plt
import pandas as pd

from generate_instance import instance_name
from model import solve
from read_data import read_data
from rq1_experiments import AXIS, GRID, INK, MUTED, SURFACE
from two_stage import solve_two_stage

# ---- settings ----
DATA = Path(__file__).parent / "data" / "instances"
RESULTS = Path(__file__).parent / "results"

METHODS = ["A", "B", "C"]
POLICY = "mixed"         # the decomposition of the paper is defined for the mixed policy
TIME_LIMIT = 600         # seconds per Gurobi call (B makes two calls, C one)
MIP_GAP = 1e-4           # Gurobi's default; 0 = solve to proven optimality
SKIP_AFTER_LIMIT = True  # a method that hits the time limit or fails is not run on larger sizes
MAX_EXACT_X = 300_000    # A and B are not built above this many x variables (services x demands),
                         # to stay within the memory of a laptop; C still runs on those networks

FINISHED = {"A": "optimal", "B": "optimal", "C": "optimal + heuristic"}  # status of a normal run


# ----------------------------------------------------------------------
# Networks: the ones generate_instance.py has made
# ----------------------------------------------------------------------
FOLDER_NAME = re.compile(r"random_V(\d+)_S(\d+)_D(\d+)_seed(\d+)$")  # see instance_name()


def generated_networks():
    """All random networks in DATA, as {(stations, services, demands): [seeds]}, smallest first.
    Sizes and seeds are set in generate_instance.py; run it first."""
    networks = {}
    for folder in DATA.iterdir():
        match = FOLDER_NAME.match(folder.name)
        if match:
            stations, services, demands, seed = map(int, match.groups())
            networks.setdefault((stations, services, demands), []).append(seed)
    if not networks:
        raise FileNotFoundError("no random networks in " + str(DATA) + ": run generate_instance.py first")
    by_size = sorted(networks, key=lambda size: (size[1] * size[2], size))  # model size = x variables
    return {size: sorted(networks[size]) for size in by_size}


NETWORKS = {}  # filled in by the main program: {(stations, services, demands): [seeds]}
SIZES = []     # the network sizes, smallest first


# ----------------------------------------------------------------------
# Runs
# ----------------------------------------------------------------------
def run_method(method, data):
    """Solve one network with one method. Returns the result and the wall-clock seconds,
    which include building the model (Gurobi's own runtime does not)."""
    start = time.perf_counter()
    if method == "A":
        result = solve(data, policy=POLICY, time_limit=TIME_LIMIT, mip_gap=MIP_GAP)
    elif method == "B":
        result = solve_two_stage(data, policy=POLICY, time_limit=TIME_LIMIT, mip_gap=MIP_GAP)
    else:
        result = solve_two_stage(data, policy=POLICY, time_limit=TIME_LIMIT, mip_gap=MIP_GAP,
                                 second_stage="greedy")
    return result, time.perf_counter() - start


def finished(method, status):
    """True if a run ended normally (not at the time limit, without a solution or with an error)."""
    return status == FINISHED[method]


def percent(difference, reference):
    """Difference in % of the reference, rounded so that rounding noise of the solver shows as 0."""
    return round(100 * difference / reference, 6) + 0.0


def run_instance(size, seed, skipped):
    """Solve one network with every method; returns one row per method."""
    stations, services, demands = size
    name = instance_name(stations, services, demands, seed)
    data = read_data(DATA / name)

    rows = {}
    for method in METHODS:
        row = {"instance": name, "stations": stations, "services": services, "demands": demands,
               "seed": seed, "x_variables": services * demands, "method": method}
        rows[method] = row
        too_large = method in ("A", "B") and services * demands > MAX_EXACT_X
        if method in skipped or too_large:
            row["status"] = "skipped" if method in skipped else "skipped: too large for memory"
            continue
        try:
            result, wall = run_method(method, data)
        except (gp.GurobiError, MemoryError) as error:  # out of memory or a Gurobi limit; code errors stop the script
            row["status"] = "failed: " + type(error).__name__
            print("failed:", name, method, error)
            continue
        if result["status"] == "no solution":
            row["status"] = "no solution"
            continue
        row.update({
            "status": result["status"],
            "profit": result["profit"],
            "bound": result.get("bound") if method == "A" else None,  # upper bound on the optimum
            "mip_gap": result.get("gap"),
            "demands_accepted": len(result["accepted"]),
            "cars_served": result["demand_served"],
            "wall_s": wall,
            "solver_s": result["runtime"],
        })
        print("done:", name, method, row["status"], "profit", round(row["profit"]), "in", round(wall, 2), "s")

    # Profit gaps. Against A's profit: negative if A stopped at the time limit with a worse plan.
    # Against A's upper bound: how far at most from the true optimum, valid even then.
    # C against B: what the greedy stage 2 loses compared with the exact stage 2.
    a, b = rows.get("A", {}), rows.get("B", {})
    for row in rows.values():
        if "profit" not in row:
            continue
        if "profit" in a:
            row["gap_to_A_%"] = percent(a["profit"] - row["profit"], a["profit"])
        if a.get("bound"):
            row["gap_to_bound_%"] = percent(a["bound"] - row["profit"], a["bound"])
        if "profit" in b:
            row["gap_to_B_%"] = percent(b["profit"] - row["profit"], b["profit"])
        if "wall_s" in a and "wall_s" in row:
            row["speedup_vs_A"] = a["wall_s"] / row["wall_s"]
    return list(rows.values())


def run_benchmark():
    rows = []
    skipped = set()
    for size, seeds in NETWORKS.items():
        size_rows = []
        for seed in seeds:
            size_rows += run_instance(size, seed, skipped)
        rows += size_rows
        if SKIP_AFTER_LIMIT:
            for row in size_rows:
                if not row["status"].startswith("skipped") and not finished(row["method"], row["status"]):
                    skipped.add(row["method"])
            if skipped:
                print("not run on larger networks:", sorted(skipped))
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------
# Summary per network size
# ----------------------------------------------------------------------
def column(frame, name):
    """A column of the runs, or an empty one if no run produced it."""
    return frame[name] if name in frame.columns else pd.Series(dtype=float)


def summarise(runs):
    """One row per network size: finished runs, runtimes, profit gaps and speed-ups."""
    rows = []
    for size in SIZES:
        stations, services, demands = size
        part = runs[(runs["stations"] == stations) & (runs["services"] == services) & (runs["demands"] == demands)]
        if part.empty:
            continue
        row = {"stations": stations, "services": services, "demands": demands,
               "x_variables": services * demands, "networks": part["seed"].nunique()}
        for method in METHODS:
            ran = part[(part["method"] == method) & ~part["status"].str.startswith("skipped")]
            row["run_" + method] = len(ran)
            row["finished_" + method] = int(sum(finished(method, s) for s in ran["status"]))
            row["time_mean_s_" + method] = column(ran, "wall_s").mean()
            row["time_max_s_" + method] = column(ran, "wall_s").max()
            if method != "A":
                row["gap_to_A_mean_%_" + method] = column(ran, "gap_to_A_%").mean()
                row["gap_to_A_max_%_" + method] = column(ran, "gap_to_A_%").max()
                row["gap_to_bound_mean_%_" + method] = column(ran, "gap_to_bound_%").mean()
                row["speedup_" + method] = row["time_mean_s_A"] / row["time_mean_s_" + method]
        if "C" in METHODS and "B" in METHODS:
            row["gap_C_to_B_mean_%"] = column(part[part["method"] == "C"], "gap_to_B_%").mean()
        rows.append(row)
    return pd.DataFrame(rows)


TITLES = {
    "rq2_runtime_s": "Runtime: wall-clock seconds incl. building the model, mean over networks",
    "rq2_finished": "Runs that finished normally (optimal, or optimal + heuristic)",
    "rq2_gap_mean_pct": "Profit gap to the exact model A, % (mean over networks; negative = better than A)",
    "rq2_gap_max_pct": "Largest profit gap to A over the networks of each size, %",
    "rq2_speedup": "Speed-up against A: mean runtime of A / mean runtime of the method",
    "rq2_greedy_loss_pct": "Profit lost by the greedy stage 2 alone: C against B, % (mean over networks)",
    "rq2_exact_vs_heuristic": "Exact solver (A) against the two-stage heuristic (C)",
}


def make_tables(summary):
    """The result tables, one row per network size (stations / services / demands). Returns {name: table}."""
    s = summary.copy()
    s.index = ["%d / %d / %d" % size for size in zip(s["stations"], s["services"], s["demands"])]
    s.index.name = "stations / services / demands"
    others = [m for m in METHODS if m != "A"]

    def pick(prefix, methods):
        table = s[[prefix + m for m in methods]].copy()
        table.columns = methods
        return table

    tables = {
        "rq2_runtime_s": pick("time_mean_s_", METHODS).round(2),
        "rq2_finished": pick("finished_", METHODS),
        "rq2_gap_mean_pct": pick("gap_to_A_mean_%_", others).round(2),
        "rq2_gap_max_pct": pick("gap_to_A_max_%_", others).round(2),
        "rq2_speedup": pick("speedup_", others).round(1),
    }
    if "gap_C_to_B_mean_%" in s.columns:
        tables["rq2_greedy_loss_pct"] = s[["gap_C_to_B_mean_%"]].rename(columns={"gap_C_to_B_mean_%": "C vs B"}).round(2)
    if "A" in METHODS and "C" in METHODS:
        networks = s["networks"].astype(str)
        tables["rq2_exact_vs_heuristic"] = pd.DataFrame({
            "exact solved": s["finished_A"].astype(str) + " / " + networks,
            "heuristic solved": s["finished_C"].astype(str) + " / " + networks,
            "exact time (s)": s["time_mean_s_A"].round(2),
            "heuristic time (s)": s["time_mean_s_C"].round(2),
            "speed-up": s["speedup_C"].round(1),
            "profit gap mean (%)": s["gap_to_A_mean_%_C"].round(2),
            "profit gap max (%)": s["gap_to_A_max_%_C"].round(2),
            "gap to A's bound (%)": s["gap_to_bound_mean_%_C"].round(2),
        })
    return tables


# ----------------------------------------------------------------------
# Figures
# ----------------------------------------------------------------------
COLOUR = {"A": "#2a78d6", "B": "#eb6834", "C": "#1baf7a"}
MARKER = {"A": "o", "B": "s", "C": "^"}
LABEL = {"A": "A: exact [OM]", "B": "B: two-stage, exact stages", "C": "C: two-stage, greedy stage 2"}


def make_figure(runs, value, methods, title, unit, filename, log=False, limit_line=False):
    """Network size on the x-axis; every network as a faint dot, the mean as a line."""
    present = set(map(tuple, runs[["stations", "services", "demands"]].values))
    sizes = [size for size in SIZES if size in present]
    position = {size: number for number, size in enumerate(sizes)}
    figure, axis = plt.subplots(figsize=(8, 4.5), facecolor=SURFACE)

    for method in methods:
        part = runs[(runs["method"] == method) & column(runs, value).notna()]
        if part.empty:
            continue
        keys = [tuple(size) for size in part[["stations", "services", "demands"]].values]
        axis.scatter([position[k] for k in keys], part[value], color=COLOUR[method], alpha=0.3, s=18, linewidths=0)
        mean = part.groupby(["stations", "services", "demands"], sort=False)[value].mean()
        axis.plot([position[k] for k in mean.index], mean.values, color=COLOUR[method], marker=MARKER[method],
                  linewidth=2, markersize=7, markeredgecolor=SURFACE, markeredgewidth=1.5, label=LABEL[method])

    if limit_line:
        axis.axhline(TIME_LIMIT, color=MUTED, linewidth=1, linestyle="--")
        axis.text(len(sizes) - 1, TIME_LIMIT, "time limit", color=MUTED, fontsize=8, ha="right", va="bottom")
    axis.set_xticks(range(len(sizes)))
    axis.set_xticklabels(["%d / %d / %d" % size for size in sizes])
    axis.set_xlabel("Stations / services / demands", fontsize=9, color=MUTED)
    axis.set_ylabel(unit, fontsize=9, color=MUTED)
    if log:
        axis.set_yscale("log")
    axis.set_facecolor(SURFACE)
    axis.grid(axis="y", color=GRID, linewidth=0.8)
    axis.set_axisbelow(True)
    axis.tick_params(colors=MUTED, labelsize=9, length=0)
    for side in ["top", "right", "left"]:
        axis.spines[side].set_visible(False)
    axis.spines["bottom"].set_color(AXIS)
    axis.set_title(title, fontsize=12, color=INK, loc="left")
    axis.legend(frameon=False, fontsize=9, labelcolor=INK)
    figure.tight_layout()
    figure.savefig(RESULTS / filename, dpi=150, facecolor=SURFACE)
    plt.close(figure)


def make_table_figure(table, title, filename):
    """A table as a picture, e.g. for slides."""
    cells = [["" if pd.isna(value) else str(value) for value in row] for row in table.values]
    figure, axis = plt.subplots(figsize=(1.6 + 1.3 * len(table.columns), 1.0 + 0.4 * len(table)), facecolor=SURFACE)
    axis.axis("off")
    grid = axis.table(cellText=cells, colLabels=list(table.columns), rowLabels=list(table.index),
                      loc="center", cellLoc="center")
    grid.auto_set_font_size(False)
    grid.set_fontsize(8.5)
    grid.scale(1, 1.4)
    for (row, col), cell in grid.get_celld().items():
        cell.set_edgecolor(GRID)
        cell.set_facecolor(SURFACE)
        cell.get_text().set_color(INK if row > 0 and col >= 0 else MUTED)
    axis.set_title(title + "\n(rows: stations / services / demands)", fontsize=10, color=INK, loc="left")
    figure.tight_layout()
    figure.savefig(RESULTS / filename, dpi=150, facecolor=SURFACE)
    plt.close(figure)


def make_figures(runs, tables):
    others = [m for m in METHODS if m != "A"]
    make_figure(runs, "wall_s", METHODS, "Runtime as the network grows",
                "Wall-clock time (s, log scale)", "rq2_runtime.png", log=True, limit_line=True)
    make_figure(runs, "gap_to_A_%", others, "Profit below the exact model",
                "Profit gap to A (%)", "rq2_profit_gap.png")
    make_figure(runs, "speedup_vs_A", others, "Speed-up against the exact model",
                "Runtime of A / runtime of the method (log scale)", "rq2_speedup.png", log=True)
    if "rq2_exact_vs_heuristic" in tables:
        make_table_figure(tables["rq2_exact_vs_heuristic"], TITLES["rq2_exact_vs_heuristic"],
                          "rq2_exact_vs_heuristic.png")


if __name__ == "__main__":
    RESULTS.mkdir(exist_ok=True)
    NETWORKS = generated_networks()
    SIZES = list(NETWORKS)
    print("networks found:", ", ".join("%d/%d/%d (seeds %s)" % (size + (seeds,)) for size, seeds in NETWORKS.items()))
    runs = run_benchmark()
    runs.to_csv(RESULTS / "rq2_runs.csv", index=False)
    tables = make_tables(summarise(runs))
    for name, table in tables.items():
        print()
        print(TITLES[name])
        print(table.to_string())
        table.to_csv(RESULTS / (name + ".csv"))
    make_figures(runs, tables)
    print()
    print("Saved the runs, " + str(len(tables)) + " tables (rq2_*.csv) and four figures (rq2_*.png) to", RESULTS)