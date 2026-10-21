"""Site weather from the free Open-Meteo API (no key needed). REQUIRES INTERNET; returns available=False offline.
Used as context (temperature affects natural frequency; heavy rain relates to moisture readings)."""
import time

import requests

_cache = {}


def current(lat, lon):
    if lat is None or lon is None:
        return {"available": False, "reason": "This structure has no coordinates."}
    key = (round(lat, 2), round(lon, 2))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=6, params={
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m"})
        r.raise_for_status()
        c = r.json().get("current", {})
        out = {"available": True, "source": "open-meteo.com", "temperature_c": c.get("temperature_2m"),
               "humidity_pct": c.get("relative_humidity_2m"), "precipitation_mm": c.get("precipitation"),
               "wind_kmh": c.get("wind_speed_10m"), "time": c.get("time")}
    except Exception as e:
        out = {"available": False, "reason": "Weather service not reachable from this server.", "detail": str(e)[:120]}
    _cache[key] = (time.time(), out)
    return out
