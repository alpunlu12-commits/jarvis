"""
Tarayıcı kontrolü — URL validation (http/https only), YouTube search encode.
"""

from __future__ import annotations

import re
import urllib.parse
import webbrowser
from typing import Optional

import requests


# ── Güvenlik: İzin verilen URL scheme'leri ────────────────────────────────────
_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http://", "https://"})
_BLOCKED_PATTERNS: tuple[str, ...] = (
    "javascript:", "data:", "file://", "vbscript:", "ftp://",
)

_VIDEO_ID_RE: re.Pattern[str] = re.compile(r'"videoId":"([A-Za-z0-9_-]{11})"')
_MAX_URL_LENGTH: int = 2048


def _validate_url(url: str) -> tuple[bool, str]:
    """
    URL'yi doğrula: sadece http/https, zararlı scheme yok.

    Returns:
        (is_valid, error_or_url)
    """
    if not url or not url.strip():
        return False, "URL belirtilmedi."

    url = url.strip()

    # Boyut kontrolü
    if len(url) > _MAX_URL_LENGTH:
        return False, f"URL çok uzun ({len(url)} karakter, max {_MAX_URL_LENGTH})."

    # Zararlı scheme kontrolü (HTTP'den önce kontrol et)
    lower = url.lower()
    for pattern in _BLOCKED_PATTERNS:
        if lower.startswith(pattern):
            return False, f"Güvenlik: '{pattern}' scheme'i engellendi."

    # HTTP/HTTPS ekle (yoksa)
    if not any(lower.startswith(s) for s in _ALLOWED_SCHEMES):
        url = "https://" + url
        lower = url.lower()

    # Tekrar kontrol (eklendikten sonra)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, f"Güvenlik: Sadece http/https izinli, '{parsed.scheme}' engellendi."

    # javascript injection kontrolü
    for pattern in _BLOCKED_PATTERNS:
        if pattern in lower:
            return False, f"Güvenlik: Zararlı URL deseni tespit edildi ({pattern})."

    return True, url


def _find_first_youtube_video(query: str) -> Optional[str]:
    """YouTube aramasından ilk video ID'sini bul."""
    encoded = urllib.parse.quote_plus(query)
    try:
        response = requests.get(
            f"https://www.youtube.com/results?search_query={encoded}",
            headers={"User-Agent": "JARVIS/1.0"},
            timeout=10,
        )
        response.raise_for_status()
        seen: set[str] = set()
        for video_id in _VIDEO_ID_RE.findall(response.text):
            if video_id not in seen:
                seen.add(video_id)
                return video_id
    except requests.RequestException:
        pass
    return None


def browser_control(
    action: str,
    url: Optional[str] = None,
    query: Optional[str] = None,
) -> str:
    """
    Tarayıcı eylemleri.

    Args:
        action: open_url, search, play_youtube, youtube_search
        url: open_url için hedef URL
        query: search/play_youtube için arama sorgusu

    Returns:
        İşlem sonucu mesajı.
    """
    if action == "open_url":
        return _open_url(url)
    elif action == "search":
        return _search(query)
    elif action in ("play_youtube", "youtube_play", "play_music"):
        return _play_youtube(query)
    elif action == "youtube_search":
        return _youtube_search(query)
    return f"Bilinmeyen eylem: '{action}'. Geçerli: open_url, search, play_youtube, youtube_search"


def _open_url(url: Optional[str]) -> str:
    """URL'yi doğrula ve aç."""
    valid, result = _validate_url(url or "")
    if not valid:
        return result
    try:
        webbrowser.open(result)
        return f"Açıldı: {result}"
    except Exception as e:
        return f"URL açılamadı: {e}"


def _search(query: Optional[str]) -> str:
    """Google'da arama yap."""
    if not query or not query.strip():
        return "Arama sorgusu belirtilmedi."
    encoded = urllib.parse.quote(query.strip())
    search_url = f"https://www.google.com/search?q={encoded}"
    try:
        webbrowser.open(search_url)
        return f"'{query.strip()}' için arama açıldı."
    except Exception as e:
        return f"Arama açılamadı: {e}"


def _play_youtube(query: Optional[str]) -> str:
    """YouTube'da ilk videoyu bul ve oynat."""
    if not query or not query.strip():
        return "YouTube için arama sorgusu belirtilmedi."

    video_id = _find_first_youtube_video(query.strip())
    if video_id:
        watch_url = f"https://www.youtube.com/watch?v={video_id}&autoplay=1"
        try:
            webbrowser.open(watch_url)
            return f"YouTube'da oynatılıyor: {query.strip()}"
        except Exception as e:
            return f"YouTube açılamadı: {e}"

    # Fallback: arama sonuçları
    encoded = urllib.parse.quote(query.strip())
    fallback = f"https://www.youtube.com/results?search_query={encoded}"
    try:
        webbrowser.open(fallback)
        return f"YouTube'da video bulunamadı, arama sonuçları açıldı: {query.strip()}"
    except Exception as e:
        return f"YouTube araması açılamadı: {e}"


def _youtube_search(query: Optional[str]) -> str:
    """YouTube'da arama sonuçlarını aç."""
    if not query or not query.strip():
        return "YouTube arama sorgusu belirtilmedi."
    encoded = urllib.parse.quote(query.strip())
    search_url = f"https://www.youtube.com/results?search_query={encoded}"
    try:
        webbrowser.open(search_url)
        return f"YouTube'da '{query.strip()}' araması açıldı."
    except Exception as e:
        return f"YouTube araması açılamadı: {e}"
