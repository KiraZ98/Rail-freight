# Mixed blocking policies under classification yard capacity limits

AMORE project, TU Dresden, winter term 2026/27. Base paper: Xin, Wu & Wang (2025),
*Rail freight transportation service network design with mixed blocking policies*.

## Layout

| Path | Content |
|---|---|
| `data/instances/toy6/` | 6-yard example for hand validation |
| `data/german/` | German yard data, capacity assumptions, distance script |
| `src/snd/instance.py` | Instance format and loader |
| `src/snd/model.py` | Simplified MILP: `solve()` and `Solution` (not yet checked against the base paper) |
| `scripts/show_instance.py` | Prints an instance summary |
| `scripts/run_toy.py` | Solves an instance under the three policies |
| `tests/test_model.py` | Hand-computed cases and consistency checks |
| `results/` | Run outputs (not tracked by git) |

## Quick start

```bash
pip install -r requirements.txt
python scripts/show_instance.py data/instances/toy6
python scripts/run_toy.py data/instances/toy6
python tests/test_model.py
```

## Instance format

One folder per instance with `nodes.csv`, `arcs.csv`, `demands.csv`,
`service_classes.csv` and `params.json`. Column names are documented at the top of
`src/snd/instance.py`. Lines in `arcs.csv` are undirected; demand is in cars per day.

All cost and revenue values in `toy6` are placeholders until they are calibrated
against the base paper.

## Interface

```python
from snd import load_instance, solve
inst = load_instance("data/instances/toy6")
sol = solve(inst, policy="mixed", yard_capacity=None, elastic=False, eps=None)
```

Everyone codes against this signature and the `Solution` fields in `src/snd/model.py`.
The modelling choices are listed at the top of that file.

`policy` is `"mixed"` (express inseparable, bulk intree), `"intree"` or `"inseparable"`
(one rule for both categories). In this model inseparable >= mixed >= intree in profit,
because each is a relaxation of the next.

## Decisions still open

1. Does the base paper already contain a hard yard capacity? Decides whether our
   extension is a new constraint or the elastic penalty.
2. Which single policy is the baseline. All-intree can only be worse than mixed and
   all-inseparable can only be better, so the baseline choice decides the sign of RQ1.
3. Reference run for the 80 % / 60 % capacity levels (proposed: mixed policy, base
   demand, no limit, per network).
4. Time limit per run and how the MIP gap is reported.
5. No transit time or detour limit yet: cars may take long detours to fill existing trains.
