"""Print a summary of an instance folder, to check it loads.

    python scripts/show_instance.py data/instances/xin2022_example
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from snd import load_instance  # noqa: E402


def main() -> None:
    folder = sys.argv[1] if len(sys.argv) > 1 else "data/instances/xin2022_example"
    inst = load_instance(folder)
    print(f"Instance {inst.name}: {len(inst.yards)} yards, {len(inst.arcs) // 2} lines, "
          f"{len(inst.services)} candidate services, {len(inst.demands)} demands")

    print("\nYards (reclassification cars/day, tracks, accumulation h, transfer h)")
    for y in inst.yards.values():
        cap = "-" if y.reclass_capacity is None else f"{y.reclass_capacity:g}"
        tracks = "-" if y.tracks is None else str(y.tracks)
        print(f"  {y.id:<4}{cap:>8}{tracks:>6}{y.accumulation_time_h:8.2f}{y.transfer_time_h:8.2f}")

    print("\nGoods categories (express, car cost per car-km)")
    for c in inst.categories.values():
        print(f"  {c.id:<12}{'yes' if c.express else 'no':<5}{c.car_cost_per_car_km:g}")

    print("\nService classes (km/h, cars per train)")
    for c in inst.service_classes.values():
        print(f"  {c.id:<5}{c.speed_kmh:6g}{c.max_cars:5d}")

    print("\nDemands")
    for d in inst.demands:
        limit = "-" if d.time_limit_h is None else f"{d.time_limit_h:g} h"
        print(f"  {d.id:<4}{d.origin}->{d.destination}  {d.category:<11}{d.cars:6g} cars/day  limit {limit}")


if __name__ == "__main__":
    main()
