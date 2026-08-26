"""
Medya açma — YouTube/Spotify arama ve oynatma (browser üzerinden).
"""

from __future__ import annotations

import urllib.parse
import webbrowser
from typing import Optional


_SPOTIFY_SEARCH_URL: str = "https://open.spotify.com/search"
_YOUTUBE_SEARCH_URL: str = "https://www.youtube.com/results?search_query="


def open_youtube_search(query: Optional[str] = None) -> str:
    """
    YouTube'da arama yap ve tarayıcıda aç.

    Args:
        query: Arama sorgusu.

    Returns:
        İşlem sonucu mesajı.
    """
    if not query or not query.strip():
        return "YouTube arama sorgusu belirtilmedi."

    safe_query = _sanitize_query(query)
    if not safe_query:
        return "Geçerli bir arama sorgusu belirtilmedi."

    encoded = urllib.parse.quote(safe_query)
    url = f"{_YOUTUBE_SEARCH_URL}{encoded}"

    try:
        webbrowser.open(url)
        return f"YouTube'da '{safe_query}' araması açıldı."
    except Exception as e:
        return f"YouTube araması açılamadı: {e}"


def open_spotify_search(query: Optional[str] = None) -> str:
    """
    Spotify'da arama yap ve tarayıcıda aç.

    Args:
        query: Arama sorgusu (şarkı, sanatçı, albüm).

    Returns:
        İşlem sonucu mesajı.
    """
    if not query or not query.strip():
        return "Spotify arama sorgusu belirtilmedi."

    safe_query = _sanitize_query(query)
    if not safe_query:
        return "Geçerli bir arama sorgusu belirtilmedi."

    encoded = urllib.parse.quote(safe_query)
    url = f"{_SPOTIFY_SEARCH_URL}/{encoded}"

    try:
        webbrowser.open(url)
        return f"Spotify'da '{safe_query}' araması açıldı."
    except Exception as e:
        return f"Spotify araması açılamadı: {e}"


def open_youtube_video(video_id: str) -> str:
    """
    Belirli bir YouTube videosunu aç.

    Args:
        video_id: 11 karakterli YouTube video ID'si.

    Returns:
        İşlem sonucu mesajı.
    """
    if not video_id or not video_id.strip():
        return "Video ID belirtilmedi."

    video_id = video_id.strip()

    # Video ID doğrulama (sadece alphanumeric, -, _)
    import re
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        return f"Geçersiz YouTube video ID: '{video_id}'"

    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        webbrowser.open(url)
        return f"YouTube video açıldı: {video_id}"
    except Exception as e:
        return f"YouTube video açılamadı: {e}"


def open_spotify_track(track_id: str) -> str:
    """
    Belirli bir Spotify parçasını aç.

    Args:
        track_id: Spotify track ID'si.

    Returns:
        İşlem sonucu mesajı.
    """
    if not track_id or not track_id.strip():
        return "Track ID belirtilmedi."

    track_id = track_id.strip()

    # Track ID doğrulama
    import re
    if not re.fullmatch(r"[A-Za-z0-9]{22}", track_id):
        return f"Geçersiz Spotify track ID: '{track_id}'"

    url = f"https://open.spotify.com/track/{track_id}"
    try:
        webbrowser.open(url)
        return f"Spotify parçası açıldı: {track_id}"
    except Exception as e:
        return f"Spotify parçası açılamadı: {e}"


def _sanitize_query(query: str) -> str:
    """
    Arama sorgusunu temizle.

    - Tehlikeli karakterleri kaldır
    - Boşlukları normalize et
    - Maksimum uzunluk kontrolü
    """
    if not query:
        return ""

    # Sadece güvenli karakterler bırak
    import re
    cleaned = re.sub(r"[^\w\sçağıöşüÇĞİÖŞÜ\-']", " ", query)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Uzunluk kontrolü
    max_len = 200
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len]

    return cleaned
