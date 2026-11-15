"""Solve an instance under the three policies and print the solutions.

    python scripts/run_toy.py data/instances/toy6
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from snd import load_instance, solve  # noqa: E402
from snd.model import POLICIES  # noqa: E402


def report(inst, sol, policy: str) -> None:
    print(f"\n=== policy: {policy} ===  status {sol.status}, gap {sol.mip_gap:.4f}, {sol.runtime_s:.2f} s")
    print(f"profit {sol.profit:,.0f}   served {sol.demand_served:.0f}/{sol.total_demand:.0f} cars/day ({sol.service_level:.0%})")
    for k, v in sol.breakdown.items():
        print(f"  {k:<22}{v:>10,.0f}")
    print("services (trains/day)")
    for (i, j, c), n in sorted(sol.frequencies.items()):
        print(f"  {i}->{j} {c:<9}{n}")
    print("demands")
    for d in inst.demands:
        route = sol.routes[d.id]
        text = "  ".join(f"{i}->{j}[{c}]" for i, j, c in route) if route else "REJECTED"
        print(f"  {d.id} {d.origin}->{d.destination} {d.category:<8}{d.cars:4.0f}  {text}")
    used = {v: t for v, t in sol.yard_throughput.items() if t > 0}
    print("cars reclassified per yard:", used or "none")


def main() -> None:
    inst = load_instance(sys.argv[1] if len(sys.argv) > 1 else "data/instances/toy6")
    for policy in POLICIES:
        report(inst, solve(inst, policy=policy), policy)


if __name__ == "__main__":
    main()
