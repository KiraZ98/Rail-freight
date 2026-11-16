"""Step 2: build and solve the service network design model with Gurobi.

The model is the one of Xin (2022), PLOS ONE 17(12): e0276671, equations (1)-(8).
Our additions are marked with "EXTENSION".
"""
import gurobipy as gp
from gurobipy import GRB

# Blocking rule used for express and for non-express goods under each policy
POLICIES = {
    "mixed":       {"express": "inseparable", "non_express": "intree"},
    "intree":      {"express": "intree",      "non_express": "intree"},
    "inseparable": {"express": "inseparable", "non_express": "inseparable"},
}


def solve(data, policy="mixed", eps=None, yard_capacity=None, penalty=None, time_limit=3600, verbose=False):
    """Solve the model and return the results as a dictionary.

    policy         "mixed", "intree" or "inseparable"
    eps            share of total demand that must be served (1.0 = all demand, as in Xin 2022)
    yard_capacity  {station: cars per day}. If None, the capacities from nodes.csv are used.
    penalty        if given, yard capacity is elastic: every car above the limit costs this much
                   (Lin et al. 2021 use 1500). If None, the capacity is a hard limit.
    time_limit     Gurobi time limit in seconds
    """
    # ------------------------------------------------------------------
    # Sets and parameters
    # ------------------------------------------------------------------
    V = data["stations"]
    S = data["services"]  # tuples (i, j, c)
    D = data["demands"]

    origin = data["origin"]
    destination = data["destination"]
    volume = data["volume"]
    revenue = data["revenue"]
    time_limit_h = data["time_limit"]
    mileage = data["mileage"]
    train_cost = data["train_cost"]
    speed = data["speed"]
    train_size = data["train_size"]
    acc_time = data["acc_time"]
    transfer_time = data["transfer_time"]

    is_express = {k: data["express"][data["category"][k]] for k in D}
    car_cost = {k: data["car_cost"][data["category"][k]] for k in D}
    total_demand = sum(volume[k] for k in D)

    if yard_capacity is None:
        yard_capacity = data["yard_capacity"]

    def leg_time(k, i, j, c):
        """Hours that shipment k needs on service (i, j, c), as in equation (4)."""
        running = mileage[i, j, c] / speed[c]
        if i == origin[k]:
            waiting = acc_time[i] * train_size[c]       # accumulation at the origin
        else:
            waiting = transfer_time[i] * train_size[c]  # transfer at an intermediate station
        return running + waiting

    # ------------------------------------------------------------------
    # Model and decision variables
    # ------------------------------------------------------------------
    m = gp.Model("service_network_design")
    m.Params.OutputFlag = 1 if verbose else 0
    m.Params.TimeLimit = time_limit

    x = m.addVars(D, S, vtype=GRB.BINARY, name="x")   # (7) x[k,i,j,c] = 1 if shipment k uses service (i,j,c)
    y = m.addVars(S, vtype=GRB.INTEGER, name="y")     # (8) y[i,j,c] = trains per day on service (i,j,c)
    z = m.addVars(D, vtype=GRB.BINARY, name="z")      # EXTENSION: z[k] = 1 if shipment k is accepted

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    # (2) Flow balance: an accepted shipment travels from its origin to its destination.
    # (3) Nonseparable shipments: it leaves every station at most once, on one service.
    for k in D:
        for v in V:
            leaving = x.sum(k, v, "*", "*")
            arriving = x.sum(k, "*", v, "*")
            if v == origin[k]:
                m.addConstr(leaving == z[k])
                m.addConstr(arriving == 0)
            elif v == destination[k]:
                m.addConstr(arriving == z[k])
                m.addConstr(leaving == 0)
            else:
                m.addConstr(leaving == arriving)
                m.addConstr(leaving <= 1)

    # (4) Transportation time limit for express goods.
    hours = {k: gp.quicksum(leg_time(k, i, j, c) * x[k, i, j, c] for (i, j, c) in S) for k in D}
    for k in D:
        if is_express[k] and k in time_limit_h:
            m.addConstr(hours[k] <= time_limit_h[k])

    # (5) Intree rule: all cars at station i with the same destination leave on the same service.
    #     tree[d,i,j,c] = 1 if cars for destination d leave station i on service (i,j,c).
    rule = {k: POLICIES[policy]["express" if is_express[k] else "non_express"] for k in D}
    intree_shipments = [k for k in D if rule[k] == "intree"]
    tree_destinations = sorted(set(destination[k] for k in intree_shipments))
    tree = m.addVars(tree_destinations, S, vtype=GRB.BINARY, name="tree")
    for k in intree_shipments:
        for (i, j, c) in S:
            m.addConstr(x[k, i, j, c] <= tree[destination[k], i, j, c])
    for d in tree_destinations:
        for v in V:
            m.addConstr(tree.sum(d, v, "*", "*") <= 1)

    # (6) Train capacity: the cars on a service must fit into its trains.
    for (i, j, c) in S:
        cars_on_service = gp.quicksum(volume[k] * x[k, i, j, c] for k in D)
        m.addConstr(cars_on_service <= train_size[c] * y[i, j, c])

    # EXTENSION: yard capacity. Cars that arrive at a station which is not their
    # destination must be reclassified there.
    reclassified = {v: gp.LinExpr() for v in V}
    for k in D:
        for (i, j, c) in S:
            if j != destination[k]:
                reclassified[j] += volume[k] * x[k, i, j, c]

    over_capacity = m.addVars(V, lb=0, name="over_capacity")  # cars above the limit (elastic case)
    for v in V:
        if v in yard_capacity and penalty is None:
            m.addConstr(reclassified[v] <= yard_capacity[v])                     # hard limit
        elif v in yard_capacity:
            m.addConstr(reclassified[v] <= yard_capacity[v] + over_capacity[v])  # elastic limit

    # EXTENSION: epsilon-constraint on the demand served (RQ3).
    demand_served = gp.quicksum(volume[k] * z[k] for k in D)
    if eps is not None:
        m.addConstr(demand_served >= eps * total_demand)

    # ------------------------------------------------------------------
    # Objective: (1) train cost + car cost, here written as profit = revenue - cost
    # ------------------------------------------------------------------
    total_revenue = gp.quicksum(revenue[k] * volume[k] * z[k] for k in D)
    total_train_cost = gp.quicksum(train_cost[s] * y[s] for s in S)
    total_car_cost = gp.quicksum(car_cost[k] * mileage[i, j, c] * volume[k] * x[k, i, j, c] for k in D for (i, j, c) in S)
    total_penalty = (penalty or 0) * over_capacity.sum()

    m.setObjective(total_revenue - total_train_cost - total_car_cost - total_penalty, GRB.MAXIMIZE)
    m.optimize()

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------
    if m.SolCount == 0:
        return {"status": "no solution"}

    # route of each shipment: follow the chosen services from the origin
    routes = {}
    for k in D:
        routes[k] = []
        station = origin[k]
        while z[k].X > 0.5 and station != destination[k]:
            next_service = [(i, j, c) for (i, j, c) in S if i == station and x[k, i, j, c].X > 0.5][0]
            routes[k].append(next_service)
            station = next_service[1]

    result = {
        "status": "optimal" if m.Status == GRB.OPTIMAL else "time limit",
        "profit": m.ObjVal,
        "revenue": total_revenue.getValue(),
        "train_cost": total_train_cost.getValue(),
        "car_cost": total_car_cost.getValue(),
        "penalty": total_penalty.getValue(),
        "demand_served": demand_served.getValue(),
        "total_demand": total_demand,
        "runtime": m.Runtime,
        "gap": m.MIPGap,
        "trains": {s: round(y[s].X) for s in S if y[s].X > 0.5},
        "routes": routes,
        "travel_time": {k: hours[k].getValue() for k in D if routes[k]},
        "reclassified": {v: reclassified[v].getValue() for v in V},
    }
    result["total_cost"] = result["train_cost"] + result["car_cost"] + result["penalty"]
    return result
