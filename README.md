# Mixed blocking policies under classification yard capacity limits

AMORE project, TU Dresden, winter term 2026/27. Base paper: Xin, Wu & Wang (2025),
*Rail freight transportation service network design with mixed blocking policies*.

**Rule for this repository: every input value comes from a cited source.** Each instance
folder has a `SOURCES.md` that names the paper table or document behind every file.
A value without a source is left blank, not guessed.

## Files

| File | What it does |
|---|---|
| `read_data.py` | Step 1: reads the CSV files of an instance into one dictionary |
| `model.py` | Step 2: builds the Gurobi model and solves it |
| `main.py` | Step 3: runs the model for the three policies and prints the results |
| `test_model.py` | Checks that the model reproduces the published result |
| `data/instances/xin2022_example/` | Published 5-station example of Xin (2022), Tables 4-8 |
| `data/german/` | German yard data (Bundestag Drucksache 19/26856) and distance script |
| `results/` | Run outputs (not tracked by git) |

## How to run

```bash
pip install -r requirements.txt
python main.py
python test_model.py
```

The instance folder and `EPS` are set at the top of `main.py`.

## How to use the model in your own script

```python
from read_data import read_data
from model import solve

data = read_data("data/instances/xin2022_example")
result = solve(data, policy="mixed", eps=1.0)
print(result["total_cost"], result["trains"], result["routes"])
```

`solve` options:

| Option | Meaning |
|---|---|
| `policy` | `"mixed"` (express inseparable, non-express intree), `"intree"` or `"inseparable"` |
| `eps` | Share of demand that must be served; `1.0` = all demand, as in Xin (2022) |
| `yard_capacity` | `{station: cars per day}`; default is the capacity column of `nodes.csv` |
| `penalty` | If given, yard capacity is elastic with this cost per car above the limit (Lin et al. 2021 use 1500) |
| `time_limit` | Gurobi time limit in seconds |

## The model

Equations (1)-(8) of Xin (2022): train cost per train, car cost per car-km, flow balance,
nonseparable shipments, time limit for express goods, intree rule, train capacity.
The equation numbers are written next to each constraint in `model.py`.

Our extensions, marked `EXTENSION` in the code: accepting or rejecting demand with revenue,
the eps-constraint on demand served, and yard reclassification capacity (hard or elastic).

## Validation

The model reproduces the published optimum of Xin (2022): 23,000 CNY with services
(1, 2, C5) x 4, (1, 4, C5) x 1 and (1, 5, C2) x 1 (Table 9). `SOURCES.md` in the
example folder explains the one inconsistency in the paper (Table 10 lists C1).

## Data format

One folder per instance:

| File | Columns |
|---|---|
| `nodes.csv` | id, name, reclass_capacity_cars_per_day, classification_tracks, accumulation_time_h, transfer_time_h |
| `categories.csv` | id, express (yes/no), car_cost_per_car_km |
| `demands.csv` | id, origin, destination, category, cars_per_day, revenue_per_car, time_limit_h |
| `service_classes.csv` | id, speed_kmh, max_cars |
| `services.csv` | origin, destination, class, mileage_km, train_cost |

A blank cell means the source gives no value.

## Still without a source

| Needed for | Value | Where to look |
|---|---|---|
| Profit objective (RQ1, RQ3) | Revenue per car | Xin, Wu & Wang (2025) |
| Yard capacity extension | Reclassification capacity and track data for a small example | Lin et al. (2021) Section 2.3 gives one yard (300 cars/day) and a 6-yard network without costs |
| German network | Train and car costs, revenues | Base paper, DB InfraGO track access charges, literature |
| German network | Demand | Destatis GENESIS 46131 |

## Decisions still open

1. Does the base paper already contain a hard yard capacity? Decides whether our
   extension is a new constraint or the elastic penalty.
2. Which single policy is the baseline. All-intree can only be worse than mixed and
   all-inseparable can only be better, so the baseline choice decides the sign of RQ1.
3. Reference run for the 80 % / 60 % capacity levels (proposed: mixed policy, base
   demand, no limit, per network).
4. Time limit per run and how the MIP gap is reported.
