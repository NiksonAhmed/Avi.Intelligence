"""Where to put a conference's pin: a built-in table of cities that host life-science conferences.

No online geocoding (nothing about Avion's plans leaves the system). A city not in the table gets no pin
and is listed with "not on the map"; add it here (one line) when the BD team uses a new city.
"""

from __future__ import annotations

import unicodedata

# city -> (latitude, longitude). Keys are lower case without accents.
CITIES: dict[str, tuple[float, float]] = {
    # North America
    "boston": (42.36, -71.06),
    "philadelphia": (39.95, -75.17),
    "new york": (40.71, -74.01),
    "washington": (38.91, -77.04),
    "washington, dc": (38.91, -77.04),
    "washington dc": (38.91, -77.04),
    "baltimore": (39.29, -76.61),
    "chicago": (41.88, -87.63),
    "san diego": (32.72, -117.16),
    "san francisco": (37.77, -122.42),
    "los angeles": (34.05, -118.24),
    "orlando": (28.54, -81.38),
    "miami": (25.76, -80.19),
    "new orleans": (29.95, -90.07),
    "atlanta": (33.75, -84.39),
    "dallas": (32.78, -96.80),
    "houston": (29.76, -95.37),
    "denver": (39.74, -104.99),
    "seattle": (47.61, -122.33),
    "las vegas": (36.17, -115.14),
    "nashville": (36.16, -86.78),
    "toronto": (43.65, -79.38),
    "montreal": (45.50, -73.57),
    "vancouver": (49.28, -123.12),
    "mexico city": (19.43, -99.13),
    # South America
    "sao paulo": (-23.55, -46.63),
    "buenos aires": (-34.60, -58.38),
    # Europe
    "london": (51.51, -0.13),
    "manchester": (53.48, -2.24),
    "edinburgh": (55.95, -3.19),
    "dublin": (53.35, -6.26),
    "paris": (48.86, 2.35),
    "lyon": (45.76, 4.84),
    "nice": (43.70, 7.27),
    "barcelona": (41.39, 2.17),
    "madrid": (40.42, -3.70),
    "lisbon": (38.72, -9.14),
    "amsterdam": (52.37, 4.90),
    "rotterdam": (51.92, 4.48),
    "brussels": (50.85, 4.35),
    "berlin": (52.52, 13.40),
    "munich": (48.14, 11.58),
    "frankfurt": (50.11, 8.68),
    "hamburg": (53.55, 9.99),
    "dusseldorf": (51.23, 6.77),
    "basel": (47.56, 7.59),
    "geneva": (46.20, 6.14),
    "zurich": (47.38, 8.54),
    "vienna": (48.21, 16.37),
    "prague": (50.08, 14.44),
    "warsaw": (52.23, 21.01),
    "budapest": (47.50, 19.04),
    "milan": (45.46, 9.19),
    "rome": (41.90, 12.50),
    "copenhagen": (55.68, 12.57),
    "stockholm": (59.33, 18.07),
    "oslo": (59.91, 10.75),
    "helsinki": (60.17, 24.94),
    "athens": (37.98, 23.73),
    "istanbul": (41.01, 28.98),
    # Middle East and Africa
    "dubai": (25.20, 55.27),
    "abu dhabi": (24.45, 54.38),
    "riyadh": (24.71, 46.68),
    "tel aviv": (32.09, 34.78),
    "cairo": (30.04, 31.24),
    "cape town": (-33.92, 18.42),
    "johannesburg": (-26.20, 28.05),
    # Asia
    "mumbai": (19.08, 72.88),
    "bangalore": (12.97, 77.59),
    "bengaluru": (12.97, 77.59),
    "hyderabad": (17.39, 78.49),
    "new delhi": (28.61, 77.21),
    "singapore": (1.35, 103.82),
    "kuala lumpur": (3.14, 101.69),
    "bangkok": (13.76, 100.50),
    "hong kong": (22.32, 114.17),
    "shanghai": (31.23, 121.47),
    "beijing": (39.90, 116.41),
    "suzhou": (31.30, 120.62),
    "guangzhou": (23.13, 113.26),
    "shenzhen": (22.54, 114.06),
    "taipei": (25.03, 121.57),
    "seoul": (37.57, 126.98),
    "tokyo": (35.68, 139.69),
    "osaka": (34.69, 135.50),
    "yokohama": (35.44, 139.64),
    # Oceania
    "sydney": (-33.87, 151.21),
    "melbourne": (-37.81, 144.96),
    "brisbane": (-27.47, 153.03),
    "perth": (-31.95, 115.86),
    "adelaide": (-34.93, 138.60),
    "auckland": (-36.85, 174.76),
}


def _key(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(plain.lower().replace(".", "").split())


def locate(city: str | None) -> tuple[float, float] | None:
    """(latitude, longitude) for a city name as typed in SharePoint, or None when unknown."""
    if not city:
        return None
    key = _key(city)
    if key in CITIES:
        return CITIES[key]
    first = key.split(",")[0].strip()  # "Boston, MA" -> "boston"
    return CITIES.get(first)
