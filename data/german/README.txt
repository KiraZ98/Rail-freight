AMORE project - network data package
====================================

AMORE_network_data.xlsx
  Yards        28 German classification yards with track counts and occupancy
               (Bundestag Drucksache 19/26856, 2021). Top 20 by tracks are marked
               as the model network. Daily capacity = tracks x throughput per track.
  Assumptions  All parameters in one place (blue/yellow cells = edit here), each with its source:
               200 cars per track (track limit per destination block, Xiao et al. 2020;
               Lin, Wang & Zhao 2021), ~76 cars per track per day (Maschen: 2 systems x
               ~4,000 wagons/day, dpa/heise 2020, / 105 tracks), 50 t net per wagon
               (EU Study on Single Wagonload Traffic 2015, reference wagon). The detour
               factor has no source and is only used for quick tests.
  Demand       Template for the Destatis table 46131 (rail freight by origin x
               destination traffic district). Converts tonnes/year to wagons/day.
  Sources & status   What is done and what is still to do.

build_distances.py
  Finds each yard's coordinates (OpenStreetMap / Nominatim, or the Latitude and Longitude columns
  of the Yards sheet) and computes shortest rail distances between the model yards on the
  OpenStreetMap main-line rail network (OSMnx + NetworkX, lecture 4 slides 26-27). Yards are
  matched to the main connected network. Outputs:
    yard_coordinates.csv     lat/lon per yard (8 yards were located by their OSM railway
                             objects because the query names in the sheet were not found)
    distance_matrix_km.csv   rail distances between the 20 model yards
    distance_method.txt      how they were computed (all pairs on the rail graph)
  The first run downloads the German rail network (about 25 minutes); OSMnx caches it in cache/.

build_german_instance.py (repository folder)
  Turns these files into model instances: data/instances/german_V19_D80_seed1..3.

Still manual
  1. Destatis GENESIS table 46131 (origin-destination): download CSV, paste into Demand, to
     replace the synthetic demand.
  2. DB Cargo planner (planner.dbcargo.com): transit times between yards, by hand.
