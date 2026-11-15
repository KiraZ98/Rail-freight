"""The one interface everybody codes against.

Role A implements `solve` (base MILP, then yard capacity extension).
Role B calls it inside the two-stage decomposition and the benchmark.
Role C calls it for the epsilon-constraint runs and reads `Solution` for metrics and plots.

Until the model exists, `solve` raises NotImplementedError. Do not change the signature or
the `Solution` fields without telling the other two.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .instance import Instance

POLICIES = ("single", "mixed")


@dataclass
class Solution:
    status: str  # "optimal", "time_limit", "infeasible"
    profit: float
    demand_served: float  # cars per day actually transported
    total_demand: float
    runtime_s: float
    mip_gap: float
    # (origin yard, destination yard, service class) -> trains per day
    frequencies: dict[tuple[str, str, str], float] = field(default_factory=dict)
    # demand id -> cars per day served (0 if rejected)
    served: dict[str, float] = field(default_factory=dict)
    # demand id -> sequence of yards the cars are reclassified at, origin and destination excluded
    reclass_yards: dict[str, list[str]] = field(default_factory=dict)
    # yard id -> cars reclassified per day
    yard_throughput: dict[str, float] = field(default_factory=dict)

    @property
    def service_level(self) -> float:
        return self.demand_served / self.total_demand if self.total_demand else 0.0


def solve(
    instance: Instance,
    policy: str = "mixed",
    yard_capacity: dict[str, float] | None = None,
    elastic: bool = False,
    eps: float | None = None,
    time_limit: float = 3600.0,
) -> Solution:
    """Solve the service network design model.

    policy         "single" or "mixed" (exact definition still to be fixed, see README).
    yard_capacity  yard id -> reclassification limit in cars per day. None = no limit
                   (the 100 % scenario). For 80 % / 60 %, pass that share of the
                   `yard_throughput` of the reference run.
    elastic        False = hard limit; True = flow above the limit is penalised with
                   params["over_capacity_penalty_per_car"].
    eps            if given, adds DemandServed >= eps * TotalDemand (RQ3).
    time_limit     Gurobi time limit in seconds.
    """
    if policy not in POLICIES:
        raise ValueError(f"policy must be one of {POLICIES}")
    raise NotImplementedError("Base MILP not implemented yet (role A, W6-W7).")
