"""Stage 6: Open-Meteo daily forecast for Curitiba, PR, Brazil."""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

# Curitiba, Paraná, Brazil
LAT = -25.4297
LON = -49.2711

# WMO Weather Interpretation Codes
_WMO: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Heavy freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm w/ slight hail", 99: "Thunderstorm w/ heavy hail",
}


PARAMS: dict = {
    "latitude": LAT,
    "longitude": LON,
    "current": ",".join([
        "temperature_2m",
        "apparent_temperature",
        "relative_humidity_2m",
        "precipitation",
        "weathercode",
        "windspeed_10m",
    ]),
    "daily": ",".join([
        "weathercode",
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "precipitation_probability_max",
        "windspeed_10m_max",
    ]),
    "timezone": "America/Sao_Paulo",
    "forecast_days": 1,
}


def fetch_weather() -> dict:
    try:
        resp = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params=PARAMS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily", {})
        current = data.get("current", {})

        def first(key: str, default=None):
            vals = daily.get(key)
            return vals[0] if vals else default

        # The daily weathercode is the *most severe* condition anywhere in the
        # 24h window, so a single afternoon cell makes the whole day read
        # "Thunderstorm". Label the card from the current observation and keep
        # the daily code only as the outlook / fallback.
        day_code = first("weathercode", 0)
        now_code = current.get("weathercode")
        code = now_code if now_code is not None else day_code

        return {
            "location": "Curitiba, PR",
            "description": _WMO.get(int(code), f"Code {code}"),
            "temp_max": first("temperature_2m_max"),
            "temp_min": first("temperature_2m_min"),
            "precipitation_mm": first("precipitation_sum", 0),
            "precip_prob": first("precipitation_probability_max"),
            "wind_max_kmh": first("windspeed_10m_max"),
            "wmo_code": day_code,
            # Current conditions
            "temp_now": current.get("temperature_2m"),
            "feels_like": current.get("apparent_temperature"),
            "humidity": current.get("relative_humidity_2m"),
            "precip_now_mm": current.get("precipitation"),
            "wind_now_kmh": current.get("windspeed_10m"),
            "current_code": now_code,
            "observed_at": current.get("time"),
        }
    except Exception as exc:
        logger.warning("Weather fetch failed: %s", exc)
        return {
            "location": "Curitiba, PR",
            "description": "Unavailable",
            "temp_max": None,
            "temp_min": None,
            "precipitation_mm": 0,
            "precip_prob": None,
            "wind_max_kmh": None,
            "wmo_code": None,
            "temp_now": None,
            "feels_like": None,
            "humidity": None,
            "precip_now_mm": None,
            "wind_now_kmh": None,
            "current_code": None,
            "observed_at": None,
        }
