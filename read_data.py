"""Step 1: read the CSV files of one instance folder.

The result is one dictionary with the sets and parameters of the model.
The names follow Tables 1 and 2 of Xin (2022).
"""
import pandas as pd


def read_data(folder):
    folder = str(folder)
    nodes = pd.read_csv(folder + "/nodes.csv", dtype={"id": str})
    categories = pd.read_csv(folder + "/categories.csv")
    demands = pd.read_csv(folder + "/demands.csv", dtype={"origin": str, "destination": str})
    classes = pd.read_csv(folder + "/service_classes.csv")
    services = pd.read_csv(folder + "/services.csv", dtype={"origin": str, "destination": str})

    data = {}

    # ---- stations (set V) ----
    data["stations"] = list(nodes["id"])
    data["acc_time"] = dict(zip(nodes["id"], nodes["accumulation_time_h"]))   # tau_AC, hours
    data["transfer_time"] = dict(zip(nodes["id"], nodes["transfer_time_h"]))  # tau_TF, hours
    # yard capacity (cars reclassified per day), only for the stations where it is given
    with_capacity = nodes.dropna(subset=["reclass_capacity_cars_per_day"])
    data["yard_capacity"] = dict(zip(with_capacity["id"], with_capacity["reclass_capacity_cars_per_day"]))

    # ---- goods categories (set P) ----
    data["express"] = dict(zip(categories["id"], categories["express"] == "yes"))
    data["car_cost"] = dict(zip(categories["id"], categories["car_cost_per_car_km"]))  # per car-km

    # ---- train service classes (set C) ----
    data["classes"] = list(classes["id"])
    data["speed"] = dict(zip(classes["id"], classes["speed_kmh"]))      # v_c, km/h
    data["train_size"] = dict(zip(classes["id"], classes["max_cars"]))  # m_c, cars per train

    # ---- train services (set S): one service = (origin, destination, class) ----
    data["services"] = list(zip(services["origin"], services["destination"], services["class"]))
    data["mileage"] = dict(zip(data["services"], services["mileage_km"]))     # l_ijc, km
    data["train_cost"] = dict(zip(data["services"], services["train_cost"]))  # c_train, per train

    # ---- demands (set D) ----
    data["demands"] = list(demands["id"])
    data["origin"] = dict(zip(demands["id"], demands["origin"]))
    data["destination"] = dict(zip(demands["id"], demands["destination"]))
    data["category"] = dict(zip(demands["id"], demands["category"]))
    data["volume"] = dict(zip(demands["id"], demands["cars_per_day"]))  # n_odp, cars per day
    # revenue per car: 0 when the source gives none
    data["revenue"] = dict(zip(demands["id"], demands["revenue_per_car"].fillna(0)))
    # time limit in hours, only for the demands that have one
    with_limit = demands.dropna(subset=["time_limit_h"])
    data["time_limit"] = dict(zip(with_limit["id"], with_limit["time_limit_h"]))

    return data
