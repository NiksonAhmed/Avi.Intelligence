"""Where to put a site's pin: Latitude/Longitude columns if the list has them, else a built-in table of
Australian cities, else the middle of the site's state. No online geocoding (nothing leaves the system)."""

from __future__ import annotations

# city -> (latitude, longitude). Lower case.
CITIES: dict[str, tuple[float, float]] = {
    "sydney": (-33.87, 151.21), "newcastle": (-32.93, 151.78), "wollongong": (-34.42, 150.89),
    "westmead": (-33.81, 150.99), "liverpool": (-33.92, 150.92), "camperdown": (-33.89, 151.18),
    "randwick": (-33.92, 151.24), "st leonards": (-33.82, 151.19), "kogarah": (-33.97, 151.13),
    "penrith": (-33.75, 150.69), "gosford": (-33.43, 151.34), "orange": (-33.28, 149.10),
    "wagga wagga": (-35.12, 147.37), "port macquarie": (-31.43, 152.91), "coffs harbour": (-30.30, 153.11),
    "tamworth": (-31.09, 150.93), "lismore": (-28.81, 153.28), "albury": (-36.08, 146.92),
    "melbourne": (-37.81, 144.96), "heidelberg": (-37.76, 145.06), "clayton": (-37.92, 145.12),
    "parkville": (-37.79, 144.95), "prahran": (-37.85, 144.99), "frankston": (-38.14, 145.12),
    "box hill": (-37.82, 145.12), "geelong": (-38.15, 144.36), "ballarat": (-37.56, 143.85),
    "bendigo": (-36.76, 144.28), "shepparton": (-36.38, 145.40), "traralgon": (-38.20, 146.54),
    "brisbane": (-27.47, 153.03), "south brisbane": (-27.48, 153.02), "herston": (-27.45, 153.03),
    "woolloongabba": (-27.49, 153.04), "chermside": (-27.39, 153.03), "gold coast": (-28.02, 153.40),
    "southport": (-27.97, 153.41), "sunshine coast": (-26.65, 153.07), "toowoomba": (-27.56, 151.95),
    "townsville": (-19.26, 146.82), "cairns": (-16.92, 145.77), "mackay": (-21.14, 149.19),
    "rockhampton": (-23.38, 150.51), "bundaberg": (-24.87, 152.35),
    "adelaide": (-34.93, 138.60), "bedford park": (-35.02, 138.57), "woodville": (-34.88, 138.54),
    "elizabeth vale": (-34.75, 138.67),
    "perth": (-31.95, 115.86), "murdoch": (-32.07, 115.84), "nedlands": (-31.97, 115.81),
    "subiaco": (-31.95, 115.82), "hollywood": (-31.97, 115.82), "joondalup": (-31.74, 115.77),
    "fremantle": (-32.06, 115.75), "bunbury": (-33.33, 115.64),
    "hobart": (-42.88, 147.33), "launceston": (-41.43, 147.14),
    "canberra": (-35.28, 149.13), "garran": (-35.34, 149.10), "bruce": (-35.25, 149.09),
    "darwin": (-12.46, 130.84), "tiwi": (-12.36, 130.88), "alice springs": (-23.70, 133.88),
}  # fmt: skip

# Middle of each state, for a site whose city is not in the table.
STATES: dict[str, tuple[float, float]] = {
    "nsw": (-32.5, 147.0), "new south wales": (-32.5, 147.0),
    "vic": (-37.0, 144.5), "victoria": (-37.0, 144.5),
    "qld": (-22.5, 145.0), "queensland": (-22.5, 145.0),
    "sa": (-30.0, 135.5), "south australia": (-30.0, 135.5),
    "wa": (-26.0, 121.5), "western australia": (-26.0, 121.5),
    "tas": (-42.0, 146.6), "tasmania": (-42.0, 146.6),
    "act": (-35.4, 149.0), "australian capital territory": (-35.4, 149.0),
    "nt": (-19.5, 133.5), "northern territory": (-19.5, 133.5),
}  # fmt: skip

STATE_SHORT = {
    "new south wales": "NSW", "victoria": "VIC", "queensland": "QLD", "south australia": "SA",
    "western australia": "WA", "tasmania": "TAS", "australian capital territory": "ACT",
    "northern territory": "NT",
}  # fmt: skip


def short_state(state: str | None) -> str:
    if not state:
        return ""
    return STATE_SHORT.get(
        state.strip().lower(), state.strip().upper() if len(state.strip()) <= 3 else state.strip()
    )


def locate(city: str | None, state: str | None) -> tuple[float, float] | None:
    if city:
        key = " ".join(city.lower().replace(".", "").split())
        if key in CITIES:
            return CITIES[key]
        first = key.split(",")[0].strip()
        if first in CITIES:
            return CITIES[first]
    if state:
        return STATES.get(state.strip().lower())
    return None
