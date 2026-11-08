"""City -> ZIP lookup for demo metros. Unknown cities fall back to model-supplied ZIPs."""
import json
import os
import re

_ZIPS = json.load(open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "zips.json")))


def city_key(city, state):
    city = (city or "").strip().lower()
    state = (state or "").strip().lower()
    if not city:
        return ""
    return f"{city}, {state}" if state else city


def zips_for(city_key_str):
    return _ZIPS.get(city_key_str, [])


def normalize_zips(zips):
    out = []
    for z in zips or []:
        m = re.search(r"\d{5}", str(z))
        if m and m.group(0) not in out:
            out.append(m.group(0))
    return out
