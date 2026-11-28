# Sources: German network

Built by `build_german_instance.py`: 19 German classification yards, 1026 services,
80 demands, demand seed 3. Running the script again gives the same files.

| File / value | Source |
|---|---|
| Yards (`nodes.csv`: id = rank, name, `tracks`) | The 20 yards with the most classification tracks; Deutscher Bundestag, Drucksache 19/26856 (2021), answer to question 4 (sheet Yards of `data/german/AMORE_network_data.xlsx`). Seddin and Seddin Süd, 0.3 km apart and on the same rail point, are merged into one node with their tracks added up (40 + 20 = 60), which gives 19 nodes |
| `latitude`, `longitude` | OpenStreetMap (Nominatim geocoding), `data/german/yard_coordinates.csv` |
| Classification and sorting capacity | tracks x 76 cars per track per day. 76 = Maschen's shunting capacity of about 2 x 4,000 wagons per day (dpa via heise online, 18.08.2020) over its 105 tracks (Bundestag 19/26856); sheet Assumptions. One yard used as a proxy for all, and the same value for cars arriving and leaving: an assumption of ours |
| Accumulation / transfer time parameter | 0.04 h / 0.02 h: average of the 139 stations of the base paper's real-world case (Xin, Wu & Wang 2025, Section 6.3.1). Chinese values; no German source found |
| Service mileage | Rail distance between the yards. Method: OSM rail graph (shortest path along main-line track) |
| Service classes, goods categories and car costs | As in the base paper (Section 6.2.1, Table 11) |
| Train cost | 50 x rail distance x 1.0 (ordinary), 1.1 (fast), 1.2 (express): equation (49) of the base paper |
| Maximal frequency | Left blank (no limit): no German source |
| Demands | Synthetic, recipe of the base paper (Section 6.1.1): random origin, destination and goods category; volume random in [1, 200] cars per day; time limit for express goods 1.2 x distance / slowest speed (47); revenue distance x volume x car cost x random(3, 4) for express, random(2, 3) otherwise (48). Distance is the rail distance |

Costs and revenues are in the base paper's units (CNY), so results are comparable with the other
instances but not real German prices. Real demand (Destatis GENESIS 46131) can replace the
synthetic demand later.
