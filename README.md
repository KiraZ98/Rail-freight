# Mixed blocking policies under classification yard capacity limits

AMORE project, TU Dresden, winter term 2026/27. Base paper: Xin, Wu & Wang (2025),
*Rail freight transportation service network design with mixed blocking policies*.

**Rule for this repository: every input value comes from a cited source.** Each instance
folder has a `SOURCES.md` that names the paper table or document behind every file.
A value without a source is left blank, not guessed.

## Layout

| Path | Content |
|---|---|
| `data/instances/xin2022_example/` | Published 5-station example of Xin (2022), Tables 4–8 |
| `data/german/` | German yard data (Bundestag Drucksache 19/26856), capacity assumptions, distance script |
| `src/snd/instance.py` | Instance format and loader |
| `src/snd/model.py` | MILP: `solve()` and `Solution` |
| `scripts/show_instance.py` | Prints an instance summary |
| `scripts/run_instance.py` | Solves an instance under the three policies |
| `tests/test_model.py` | Reproduces the published result and checks the model |
| `results/` | Run outputs (not tracked by git) |

## Quick start

```bash
pip install -r requirements.txt
python scripts/show_instance.py data/instances/xin2022_example
python scripts/run_instance.py data/instances/xin2022_example 1.0
python tests/test_model.py
```

## Validation

The model reproduces the published optimum of Xin (2022): 23,000 CNY with services
(1, 2, C5) x 4, (1, 4, C5) x 1 and (1, 5, C2) x 1 (Table 9). `SOURCES.md` in the
example folder explains the one inconsistency in the paper (Table 10 lists C1).

## Model

Equations (1)–(8) of Xin (2022): train cost per train, car cost per car-km, flow balance,
nonseparable shipments, time limit for express goods, train capacity. The tree-shaped path
rule (eq. 5) is implemented as the intree blocking rule.

Optional extensions, switched off when their data are not given: revenue with demand
rejection and the eps-constraint, yard reclassification capacity (hard or elastic, Lin et
al. 2021), line capacity, reclassification and accumulation cost.

`policy` is `"mixed"` (express inseparable, non-express intree), `"intree"` or
`"inseparable"`. In this model inseparable <= mixed <= intree in cost, because each is a
relaxation of the next.

## Instance format

Column names are documented at the top of `src/snd/instance.py`. Candidate services come
from `services.csv` (origin, destination, class, mileage, cost per train) when it exists,
as in Xin (2022); otherwise they are generated on shortest paths from `arcs.csv`.

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
