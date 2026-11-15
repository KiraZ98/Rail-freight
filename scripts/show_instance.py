"""Print a summary of an instance folder, to check it loads and for hand validation.

    python scripts/show_instance.py data/instances/toy6
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from snd import load_instance  # noqa: E402


def main() -> None:
    folder = sys.argv[1] if len(sys.argv) > 1 else "data/instances/toy6"
    inst = load_instance(folder)
    dist = inst.shortest_distances()

    print(f"Instance {inst.name}: {len(inst.yards)} yards, {len(inst.arcs) // 2} lines, {len(inst.demands)} demands")
    print("\nYards (reclassification cars/day, classification tracks)")
    for y in inst.yards.values():
        print(f"  {y.id}  {y.reclass_capacity:6.0f}  {y.tracks:3d}")

    print("\nShortest distances (km)")
    ids = list(inst.yards)
    print("     " + "".join(f"{j:>6}" for j in ids))
    for i in ids:
        print(f"  {i:<3}" + "".join(f"{dist.get((i, j), 0):6.0f}" for j in ids))

    print("\nDemands")
    for d in inst.demands:
        km = dist[d.origin, d.destination]
        print(f"  {d.id}  {d.origin}->{d.destination}  {d.category:<7} {d.cars:5.0f} cars/day  {km:4.0f} km  revenue {d.revenue_per_car:6.0f}/car")
    for cat in ("express", "bulk"):
        print(f"  total {cat}: {sum(d.cars for d in inst.demands if d.category == cat):.0f} cars/day")
    print(f"  maximum revenue if everything is served: {sum(d.cars * d.revenue_per_car for d in inst.demands):,.0f} per day")


if __name__ == "__main__":
    main()
