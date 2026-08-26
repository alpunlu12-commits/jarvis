"""
Hava durumu — wttr.in API (API key'siz, ücretsiz).
"""

from __future__ import annotations

import os
from typing import Optional

import requests


_BASE_URL: str = "https://wttr.in"
_TIMEOUT: int = 10
_USER_AGENT: str = "JARVIS/1.0"


def get_weather(location: Optional[str] = None) -> str:
    """
    Hava durumu bilgisini al.

    Args:
        location: Şehir adı (varsayılan: JARVIS_WEATHER_LOCATION env veya Istanbul).

    Returns:
        Biçimlendirilmiş hava durumu özeti.
    """
    target = (
        (location or "").strip()
        or os.environ.get("JARVIS_WEATHER_LOCATION", "")
        or "Istanbul"
    ).strip()

    try:
        response = requests.get(
            f"{_BASE_URL}/{target}",
            params={"format": "j1"},
            timeout=_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
        )
        response.raise_for_status()
    except requests.Timeout:
        return f"Hava durumu isteği zaman aşımına uğradı ({_TIMEOUT}s)."
    except requests.ConnectionError:
        return "Hava durumu servisine bağlanılamadı (internet kontrol edin)."
    except requests.HTTPError as e:
        return f"Hava durumu servisi hata döndürdü: {e.response.status_code}"
    except requests.RequestException as e:
        return f"Hava durumu alınamadı: {e}"

    try:
        payload = response.json()
    except ValueError:
        return "Hava durumu verisi işlenemedi (geçersiz JSON)."

    return _format_weather(target, payload)


def _format_weather(location: str, payload: dict) -> str:
    """JSON yanıtını okunabilir metne çevir."""
    conditions = payload.get("current_condition")
    if not conditions or not isinstance(conditions, list):
        return "Hava durumu bilgisi şu anda alınamadı."

    current = conditions[0]
    temp_c = current.get("temp_C", "")
    feels_like = current.get("FeelsLikeC", "")
    humidity = current.get("humidity", "")
    wind_speed = current.get("windspeedKmph", "")
    wind_dir = current.get("winddir16Point", "")

    # Hava durumu açıklaması
    weather_desc_list = current.get("weatherDesc", [])
    weather_desc = ""
    if weather_desc_list and isinstance(weather_desc_list, list):
        weather_desc = weather_desc_list[0].get("value", "")

    parts: list[str] = []
    if temp_c:
        parts.append(f"{temp_c}°C")
    if weather_desc:
        parts.append(weather_desc.lower())
    if feels_like and feels_like != temp_c:
        parts.append(f"hissedilen {feels_like}°C")
    if humidity:
        parts.append(f"nem %{humidity}")
    if wind_speed:
        wind_info = f"rüzgar {wind_speed} km/sa"
        if wind_dir:
            wind_info += f" ({wind_dir})"
        parts.append(wind_info)

    if not parts:
        return "Hava durumu bilgisi şu anda alınamadı."

    return f"{location} için hava durumu: {', '.join(parts)}."
