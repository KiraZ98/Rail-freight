# Mixed blocking policies under classification yard capacity limits

AMORE project, TU Dresden, winter term 2026/27. Base paper: Xin, Wu & Wang (2025),
*Rail freight transportation service network design with mixed blocking policies*,
Journal of Rail Transport Planning & Management 33, 100495.

**Rule for this repository: every input value comes from a cited source.** Each instance
folder has a `SOURCES.md` that names the paper table or document behind every file.
A value without a source is left blank, not guessed.

## Files

| File | What it does |
|---|---|
| `read_data.py` | Step 1: reads the CSV files of an instance into one dictionary |
| `model.py` | Step 2: builds the Gurobi model and solves it |
| `main.py` | Step 3: runs the model for the three policies and prints the results |
| `test_model.py` | Checks that the model reproduces the published results |
| `data/instances/xin2025_example/` | 8-station case of the base paper (Tables 10-12 and its services file) |
| `data/instances/xin2022_example/` | 5-station example of Xin (2022), Tables 4-8 |
| `data/german/` | German yard data (Bundestag Drucksache 19/26856) and distance script |
| `results/` | Run outputs (not tracked by git) |

## How to run

```bash
pip install -r requirements.txt
python main.py
python test_model.py
```

The instance folder, `EPS` and `CAPACITY_FACTOR` are set at the top of `main.py`.

## How to use the model in your own script

```python
from read_data import read_data
from model import solve

data = read_data("data/instances/xin2025_example")
result = solve(data, policy="mixed", capacity_factor=0.8)
print(result["profit"], result["accepted"], result["routes"])
```

`solve` options:

| Option | Meaning |
|---|---|
| `policy` | `"mixed"` (express inseparable, non-express intree), `"intree"` or `"inseparable"` |
| `eps` | Share of demand (in cars) that must be served; `None` = the model decides |
| `capacity_factor` | Multiplies the classification and sorting capacity of every station (`0.8` = 80 %) |
| `penalty` | If given, station capacity is elastic with this cost per car above the limit (Lin et al. 2021 use 1500) |
| `integer_trains` | `False` = fractional trains per day as in the base paper; `True` = whole trains as in Xin (2022) |
| `time_limit` | Gurobi time limit in seconds |

`data` is a plain dictionary, so single values can be changed before solving, for example
`data["classification_capacity"]["3"] = 500`.

## The model

Model [OM] of the base paper, equations (1)-(13): profit objective, flow conservation,
one service per leg, time limit for express demands, intree rule for non-express demands,
classification and sorting capacity per station, train capacity, maximal service frequency.
The equation numbers are written next to each constraint in `model.py`.

The intree rule is written with one "tree" variable per destination instead of the paper's
pairwise constraints (5). Both forms allow the same solutions; ours needs far fewer constraints.

Our extensions, marked `EXTENSION` in the code: the capacity factor, elastic capacity with a
penalty, and the eps-constraint on demand served.

## Validation

| Published result | Paper | Our model |
|---|---|---|
| Base paper, 8-station case (Table 12): profit | 7,154,039.94 CNY | 7,154,039.94 CNY |
| total costs | 10,399,404.06 CNY | 10,399,404.06 CNY |
| accepted shipments | 26 of 30 | 26 of 30, same four rejected, same routes |
| Xin (2022), 5-station example: cost | 23,000 CNY | 23,000 CNY |

## First observations on the 8-station case (preliminary)

- At the published capacities no station is more than 32 % used, so the capacity
  constraints (6) and (7) are not active in the paper's own example.
- Profit by policy at the published capacities: inseparable 7,160,783, mixed 7,154,040,
  intree 6,617,672 CNY.
- Scaling all station capacities down has no effect until about 30 %. Below that the gap
  between mixed and intree shrinks and is zero at 20 % and below.

One instance only; not a result for the report yet.

## Data format

One folder per instance:

| File | Columns |
|---|---|
| `nodes.csv` | id, name, accumulation_time_h, transfer_time_h, classification_capacity, sorting_capacity |
| `categories.csv` | id, express (yes/no), car_cost_per_car_km |
| `demands.csv` | id, origin, destination, category, cars_per_day, time_limit_h, revenue (whole demand) |
| `service_classes.csv` | id, speed_kmh, max_cars |
| `services.csv` | origin, destination, class, mileage_km, train_cost (per train), max_frequency |

A blank cell means the source gives no value.

## Still to do

| Item | Source to use |
|---|---|
| Practical two-stage approach (Table 13: 5,656,936.41 CNY) | Base paper, Fig. 3(a) and Section 6.2.3 |
| Greedy heuristic for the second stage (RQ2) | Base paper, Algorithm 2 |
| Random instances (RQ2) | Base paper, Section 6.1.1, equations (47)-(49) |
| Track limit per yard (one track per 200 cars) | Lin et al. (2021), constraint (14) |
| German network: costs and revenues | Base paper formulas (48)-(49) applied to German distances; DB InfraGO track access charges |
| German network: demand | Destatis GENESIS 46131 |

## Decisions

1. **Yard capacity in the base paper:** yes, hard limits (6) and (7). Our contribution is to
   vary them, make them elastic and add the track limit.
2. **Baseline policy:** the paper compares mixed with both single policies (Table 15).
   We do the same; intree is the headline baseline.
3. **Open:** how to define the capacity levels. The paper's capacities only bind below about
   30 % of their published values, so "80 % and 60 %" of them would change nothing.
4. **Open:** time limit per run and how the MIP gap is reported.
