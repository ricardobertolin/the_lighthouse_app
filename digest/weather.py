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


def fetch_weather() -> dict:
    try:
        resp = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": LAT,
                "longitude": LON,
                "daily": ",".join([
                    "weathercode",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_sum",
                    "windspeed_10m_max",
                ]),
                "timezone": "America/Sao_Paulo",
                "forecast_days": 1,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily", {})

        def first(key: str, default=None):
            vals = daily.get(key)
            return vals[0] if vals else default

        code = first("weathercode", 0)
        return {
            "location": "Curitiba, PR",
            "description": _WMO.get(int(code), f"Code {code}"),
            "temp_max": first("temperature_2m_max"),
            "temp_min": first("temperature_2m_min"),
            "precipitation_mm": first("precipitation_sum", 0),
            "wind_max_kmh": first("windspeed_10m_max"),
            "wmo_code": code,
        }
    except Exception as exc:
        logger.warning("Weather fetch failed: %s", exc)
        return {
            "location": "Curitiba, PR",
            "description": "Unavailable",
            "temp_max": None,
            "temp_min": None,
            "precipitation_mm": 0,
            "wind_max_kmh": None,
            "wmo_code": None,
        }
