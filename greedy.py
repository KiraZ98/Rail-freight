"""Revenue-aware greedy heuristic for the second stage [TM-2].

Algorithm 2 of Xin, Wu & Wang (2025), Journal of Rail Transport Planning & Management 33,
100495, Section 5.3, with its shortest path routine (Algorithm 3, Appendix A).

The demands are taken one by one, highest revenue first (line 2). For each demand, every
service it may still use gets a cost (lines 4-20); the cheapest path over these services is
found (line 21); the demand is accepted if that path costs less than its revenue, and the
capacities are reduced (lines 22-35). A decision is never undone.

Input: the same data dictionary as for model.solve. In the two-stage approach, two_stage.py
passes the capacities that stage 1 left over, (44)-(46). Output: the same keys as model.solve.

Three details the pseudo code leaves open, decided here:
* Between two stations, the cheapest usable service class is kept (lines 11 and 16 only
  overwrite the cost; we keep the minimum).
* Train costs are marginal: with fractional trains (the paper) n / m_c trains per service,
  as in lines 6-7; with whole trains, only the extra trains that the demand makes necessary.
* EXTENSION: with track_limit, a service is only usable if the station still has the sorting
  tracks for it (Xiao et al. 2020, constraints (8)-(10)), as in model.py.
"""
import heapq
import math
import time

from model import POLICIES


def solve_greedy(data, policy="mixed", capacity_factor=1.0, integer_trains=False,
                 track_limit=False, cars_per_track=200):
    """Run Algorithm 2 on the demands of `data` and return the results as a dictionary.

    policy           "mixed", "intree" or "inseparable": decides which demands follow the intree rule
    capacity_factor  multiplies the station capacities (two_stage.py has already applied it)
    integer_trains   False = fractional trains per day as in the paper; True = whole trains
    track_limit      EXTENSION: respect the sorting tracks per station in data["tracks"]
    cars_per_track   cars one track can hold (200 in Xiao et al. 2020)
    """
    start = time.perf_counter()

    # ------------------------------------------------------------------
    # Sets and parameters (the same names as in model.py)
    # ------------------------------------------------------------------
    V = data["stations"]
    S = data["services"]
    D = data["demands"]

    origin = data["origin"]
    destination = data["destination"]
    volume = data["volume"]
    revenue = data["revenue"]
    mileage = data["mileage"]
    train_cost = data["train_cost"]
    max_frequency = data["max_frequency"]
    train_size = data["train_size"]

    is_express = {k: data["express"][data["category"][k]] for k in D}
    car_cost = {k: data["car_cost"][data["category"][k]] for k in D}
    rule = {k: POLICIES[policy]["express" if is_express[k] else "non_express"] for k in D}

    for k in D:
        if is_express[k] and k in data["time_limit"]:
            raise ValueError("the greedy heuristic does not check time limits (4); "
                             "use it for the non-express demands of stage 2 only")
    if track_limit and not data.get("tracks"):
        raise ValueError("track_limit=True, but the instance has no track counts")

    # ------------------------------------------------------------------
    # What is still free: (44)-(46). Stations or services without a value have no limit.
    # ------------------------------------------------------------------
    remaining_in = {v: capacity_factor * cap for v, cap in data["classification_capacity"].items()}
    remaining_out = {v: capacity_factor * cap for v, cap in data["sorting_capacity"].items()}
    tracks_available = dict(data["tracks"]) if track_limit else {}

    cars_on = {s: 0 for s in S}   # cars on each service so far
    trains = {s: 0 for s in S}    # trains per day on each service so far
    tree = {}                     # (destination, station) -> service: the intree rule (5)
    routes = {k: [] for k in D}
    accepted = []

    def trains_for(s, cars):
        """Trains per day that `cars` cars need on service s."""
        if integer_trains:
            return math.ceil(round(cars / train_size[s[2]], 9))
        return cars / train_size[s[2]]

    def tracks_for(cars):
        """Sorting tracks that one block of `cars` cars needs: step function (9) of Xiao et al."""
        return math.ceil(round(cars / cars_per_track, 9))

    tracks_used = {v: 0 for v in V}

    # ------------------------------------------------------------------
    # Algorithm 2
    # ------------------------------------------------------------------
    order = sorted(D, key=lambda k: (-revenue[k], str(k)))  # line 2: highest revenue first
    for k in order:                                          # line 3
        n = volume[k]
        d = destination[k]

        # Lines 4-20: the cheapest usable service between every pair of stations
        cheapest = {}  # (i, j) -> (cost, service)
        for s in S:
            i, j, c = s
            # lines 9 and 15: intree rule. If cars for d already leave station i, only that service
            if rule[k] == "intree" and tree.get((d, i), s) != s:
                continue
            # line 10: remaining classification (32) and sorting (33) capacity
            if j in remaining_in and n > remaining_in[j] + 1e-9:
                continue
            if i in remaining_out and n > remaining_out[i] + 1e-9:
                continue
            # line 10: remaining service frequency (35)
            extra_trains = trains_for(s, cars_on[s] + n) - trains[s]
            if s in max_frequency and trains[s] + extra_trains > max_frequency[s] + 1e-9:
                continue
            # EXTENSION: sorting tracks at station i
            if i in tracks_available:
                extra_tracks = tracks_for(cars_on[s] + n) - tracks_for(cars_on[s])
                if tracks_used[i] + extra_tracks > tracks_available[i]:
                    continue
            # lines 6-8 and 11: train costs and car costs, as in objective (28)
            cost = train_cost[s] * extra_trains + car_cost[k] * mileage[s] * n
            if (i, j) not in cheapest or cost < cheapest[i, j][0]:
                cheapest[i, j] = (cost, s)

        # Line 21: cheapest path from origin to destination
        cost, path = shortest_path(cheapest, origin[k], d)

        # Lines 22-35: accept the demand if it pays, and reduce what is still free
        if path is None or cost >= revenue[k]:
            continue
        accepted.append(k)
        routes[k] = path
        for s in path:
            i, j, c = s
            tracks_used[i] += tracks_for(cars_on[s] + n) - tracks_for(cars_on[s])
            cars_on[s] += n
            trains[s] = trains_for(s, cars_on[s])
            if j in remaining_in:
                remaining_in[j] -= n
            if i in remaining_out:
                remaining_out[i] -= n
            if rule[k] == "intree":
                tree[d, i] = s

    # ------------------------------------------------------------------
    # Results, with the same keys as model.solve
    # ------------------------------------------------------------------
    accepted = [k for k in D if k in accepted]  # in the order of the data
    total_revenue = sum(revenue[k] for k in accepted)
    total_train_cost = sum(train_cost[s] * trains[s] for s in S)
    total_car_cost = sum(car_cost[k] * mileage[s] * volume[k] for k in accepted for s in routes[k])

    classified = {v: 0 for v in V}
    sorted_cars = {v: 0 for v in V}
    reclassified = {v: 0 for v in V}
    for k in accepted:
        for (i, j, c) in routes[k]:
            sorted_cars[i] += volume[k]
            classified[j] += volume[k]
            if j != destination[k]:
                reclassified[j] += volume[k]

    result = {
        "status": "heuristic",
        "profit": total_revenue - total_train_cost - total_car_cost,
        "revenue": total_revenue,
        "train_cost": total_train_cost,
        "car_cost": total_car_cost,
        "penalty": 0.0,
        "accepted": accepted,
        "demand_served": sum(volume[k] for k in accepted),
        "total_demand": sum(volume[k] for k in D),
        "runtime": time.perf_counter() - start,
        "gap": None,  # a heuristic has no bound
        "trains": {s: round(t, 6) for s, t in trains.items() if t > 1e-6},
        "routes": routes,
        "travel_time": {k: travel_time(data, k, routes[k]) for k in accepted},
        "classified": classified,
        "sorted": sorted_cars,
        "reclassified": reclassified,
        "tracks_used": {v: sum(tracks_for(cars_on[s]) for s in S if s[0] == v) for v in V},
    }
    result["total_cost"] = result["train_cost"] + result["car_cost"]
    return result


def shortest_path(edges, origin, destination):
    """Algorithm 3 of the paper (Appendix A): Dijkstra's algorithm, stopped as soon as the
    destination is labelled.

    edges  {(i, j): (cost, service)}
    Returns (cost, list of services from origin to destination), or (inf, None) if there is no path.
    """
    leaving = {}
    for (i, j), (cost, s) in edges.items():
        leaving.setdefault(i, []).append((j, cost, s))

    distance = {origin: 0.0}
    arrived_by = {}  # station -> service used to reach it
    done = set()
    heap = [(0.0, str(origin), origin)]
    while heap:
        cost, _, i = heapq.heappop(heap)
        if i in done:
            continue
        if i == destination:
            break
        done.add(i)
        for j, edge_cost, s in leaving.get(i, []):
            if j not in done and cost + edge_cost < distance.get(j, math.inf) - 1e-9:
                distance[j] = cost + edge_cost
                arrived_by[j] = s
                heapq.heappush(heap, (distance[j], str(j), j))

    if destination not in distance:
        return math.inf, None
    path = []
    station = destination
    while station != origin:
        s = arrived_by[station]
        path.append(s)
        station = s[0]
    return distance[destination], path[::-1]


def travel_time(data, k, route):
    """Hours that demand k needs on its route, as in equation (4) and model.leg_time."""
    hours = 0.0
    for (i, j, c) in route:
        hours += data["mileage"][i, j, c] / data["speed"][c]
        if i == data["origin"][k]:
            hours += data["acc_time"][i] * data["train_size"][c]
        else:
            hours += data["transfer_time"][i] * data["train_size"][c]
    return hours