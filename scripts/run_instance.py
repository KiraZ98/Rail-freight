"""Solve an instance under the three blocking policies and print the solutions.

    python scripts/run_instance.py data/instances/xin2022_example 1.0

The optional second argument is eps (share of demand that must be served).
Use 1.0 for instances without revenue data, such as the Xin (2022) example.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from snd import load_instance, solve  # noqa: E402
from snd.model import POLICIES  # noqa: E402


def report(inst, sol, policy: str) -> None:
    print(f"\n=== policy: {policy} ===  status {sol.status}, gap {sol.mip_gap:.4f}, {sol.runtime_s:.2f} s")
    print(f"profit {sol.profit:,.2f}   total cost {sol.total_cost:,.2f}   "
          f"served {sol.demand_served:g}/{sol.total_demand:g} cars/day ({sol.service_level:.0%})")
    for k, v in sol.breakdown.items():
        print(f"  {k:<22}{v:>12,.2f}")
    print("services (trains/day)")
    for (i, j, c), n in sorted(sol.frequencies.items()):
        print(f"  {i}->{j} {c:<5}{n}")
    print("demands")
    for d in inst.demands:
        route = sol.routes[d.id]
        text = "  ".join(f"{i}->{j}[{c}]" for i, j, c in route) if route else "REJECTED"
        t = f"  {sol.travel_time_h[d.id]:.2f} h" if d.id in sol.travel_time_h else ""
        print(f"  {d.id} {d.origin}->{d.destination} {d.category:<10}{d.cars:5g}  {text}{t}")
    used = {v: t for v, t in sol.yard_throughput.items() if t > 0}
    print("cars reclassified per yard:", used or "none")


def main() -> None:
    folder = sys.argv[1] if len(sys.argv) > 1 else "data/instances/xin2022_example"
    eps = float(sys.argv[2]) if len(sys.argv) > 2 else None
    inst = load_instance(folder)
    for policy in POLICIES:
        report(inst, solve(inst, policy=policy, eps=eps), policy)


if __name__ == "__main__":
    main()
