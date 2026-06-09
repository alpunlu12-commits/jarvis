# Alp Ünlü tarafından yapılmıştır — @alppunlu
from __future__ import annotations

import datetime as dt
import re
from urllib.parse import urlparse

import requests

from app_config import get_app_config_value


API_ROOT = "https://www.googleapis.com/youtube/v3"
DEFAULT_VIDEO_LIMIT = 6
TIMEOUT = 14
CHANNEL_ID_RE = re.compile(r"^UC[a-zA-Z0-9_-]{22}$")
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
ISO_DURATION_RE = re.compile(r"PT(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?")


def _format_int(value: int) -> str:
    return f"{int(value):,}".replace(",", ".")


def _parse_duration_seconds(raw: str) -> int:
    match = ISO_DURATION_RE.match(raw or "")
    if not match:
        return 0
    hours = int(match.group("h") or 0)
    minutes = int(match.group("m") or 0)
    seconds = int(match.group("s") or 0)
    return hours * 3600 + minutes * 60 + seconds


def _format_duration(raw: str) -> str:
    total = _parse_duration_seconds(raw)
    if total <= 0:
        return ""
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}s {minutes}dk"
    if minutes:
        return f"{minutes}dk {seconds:02d}sn"
    return f"{seconds}sn"


def _parse_dt(raw: str) -> dt.datetime | None:
    if not raw:
        return None
    try:
        return dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def _days_ago_text(published_at: str) -> str:
    published = _parse_dt(published_at)
    if not published:
        return ""
    now = dt.datetime.now(dt.timezone.utc)
    delta = now - published.astimezone(dt.timezone.utc)
    days = max(0, delta.days)
    if days == 0:
        return "bugün"
    if days == 1:
        return "dün"
    return f"{days} gün önce"


def _average(values: list[int]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _normalize_channel_ref(raw: str) -> tuple[str | None, str]:
    value = str(raw or get_app_config_value("youtube_channel_handle", "") or "").strip()
    if not value:
        return None, ""

    if value.startswith("@"):
        return "forHandle", value

    if CHANNEL_ID_RE.match(value):
        return "id", value

    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        host = parsed.netloc.lower()
        if host in YOUTUBE_HOSTS:
            path = parsed.path.strip("/")
            if path.startswith("@"):
                return "forHandle", path
            if path.startswith("channel/"):
                channel_id = path.split("/", 1)[1].strip()
                if channel_id:
                    return "id", channel_id

    return "forHandle", value if value.startswith("@") else f"@{value}"


def _api_get(endpoint: str, params: dict, api_key: str) -> dict:
    response = requests.get(
        f"{API_ROOT}/{endpoint}",
        params={**params, "key": api_key},
        timeout=TIMEOUT,
        headers={"User-Agent": "JARVIS macOS"},
    )
    if response.ok:
        return response.json()

    try:
        payload = response.json()
    except Exception:
        payload = {}

    error = payload.get("error") or {}
    reasons = error.get("errors") or []
    reason = ""
    if reasons and isinstance(reasons[0], dict):
        reason = str(reasons[0].get("reason", "") or "")
    message = str(error.get("message", "") or "")

    if reason == "keyInvalid":
        raise RuntimeError("YouTube API anahtari gecersiz gorunuyor.")
    if reason == "quotaExceeded":
        raise RuntimeError("YouTube API kotasi su anda dolu gorunuyor.")
    if reason in {"accessNotConfigured", "forbidden"}:
        raise RuntimeError("YouTube Data API bu anahtar icin aktif degil veya erisim engelli.")
    if response.status_code == 404:
        raise RuntimeError("YouTube verisi bulunamadi.")
    raise RuntimeError(message or f"YouTube API hatasi ({response.status_code}).")


def _fetch_channel_payload(channel_ref: str, api_key: str) -> tuple[dict, str]:
    filter_name, filter_value = _normalize_channel_ref(channel_ref)
    if not filter_name or not filter_value:
        raise RuntimeError("YouTube kanal handle'i ayarlanmamis. Ayarlardan @handle gir.")

    payload = _api_get(
        "channels",
        {
            "part": "snippet,statistics,contentDetails",
            filter_name: filter_value,
            "maxResults": 1,
        },
        api_key,
    )
    items = payload.get("items") or []
    if not items:
        raise RuntimeError(
            f"YouTube kanalini bulamadim. Ayarlardaki kanal handle alanina '{filter_value}' benzeri bir deger gir."
        )
    return items[0], filter_value


def _fetch_recent_videos(uploads_playlist_id: str, api_key: str, video_limit: int) -> list[dict]:
    playlist_payload = _api_get(
        "playlistItems",
        {
            "part": "snippet,contentDetails",
            "playlistId": uploads_playlist_id,
            "maxResults": max(1, min(10, video_limit)),
        },
        api_key,
    )
    items = playlist_payload.get("items") or []
    if not items:
        return []

    by_id = {}
    ordered_ids = []
    for item in items:
        snippet = item.get("snippet") or {}
        details = item.get("contentDetails") or {}
        video_id = (
            details.get("videoId")
            or ((snippet.get("resourceId") or {}).get("videoId"))
        )
        if not video_id:
            continue
        ordered_ids.append(video_id)
        by_id[video_id] = {
            "video_id": video_id,
            "title": snippet.get("title", ""),
            "published_at": snippet.get("publishedAt", ""),
        }

    if not ordered_ids:
        return []

    videos_payload = _api_get(
        "videos",
        {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(ordered_ids),
        },
        api_key,
    )

    for item in videos_payload.get("items") or []:
        video_id = item.get("id", "")
        if video_id not in by_id:
            continue
        snippet = item.get("snippet") or {}
        stats = item.get("statistics") or {}
        by_id[video_id].update(
            {
                "title": snippet.get("title") or by_id[video_id]["title"],
                "published_at": snippet.get("publishedAt") or by_id[video_id]["published_at"],
                "views": int(stats.get("viewCount") or 0),
                "likes": int(stats.get("likeCount") or 0),
                "comments": int(stats.get("commentCount") or 0),
                "duration": item.get("contentDetails", {}).get("duration", ""),
            }
        )

    return [by_id[video_id] for video_id in ordered_ids if video_id in by_id]


def _trend_sentence(videos: list[dict]) -> str:
    if len(videos) < 4:
        return ""
    split = max(2, len(videos) // 2)
    recent = videos[:split]
    older = videos[split:]
    recent_avg = _average([video.get("views", 0) for video in recent])
    older_avg = _average([video.get("views", 0) for video in older])
    if older_avg <= 0:
        return ""
    ratio = recent_avg / older_avg
    if ratio >= 1.18:
        return "Son videolar onceki gruba gore daha guclu performans gosteriyor."
    if ratio <= 0.82:
        return "Son videolar onceki gruba gore biraz daha yavas gidiyor."
    return "Son videolarin performansi genel olarak dengeli."


def get_youtube_channel_report(query: str = "overview", handle: str = "", video_limit: int = DEFAULT_VIDEO_LIMIT) -> str:
    api_key = str(get_app_config_value("youtube_api_key", "") or "").strip()
    if not api_key:
        return (
            "YouTube istatistikleri icin once YouTube API Key gerekli. "
            "Ayarlar > API Settings icinden YouTube API anahtarini gir."
        )

    try:
        channel, channel_ref = _fetch_channel_payload(handle, api_key)
        snippet = channel.get("snippet") or {}
        statistics = channel.get("statistics") or {}
        uploads_id = ((channel.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads", "")

        channel_title = snippet.get("title", "YouTube kanalin")
        custom_url = str(snippet.get("customUrl", "") or "").strip()
        display_handle = custom_url if custom_url.startswith("@") else channel_ref
        subscribers = int(statistics.get("subscriberCount") or 0)
        total_views = int(statistics.get("viewCount") or 0)
        video_count = int(statistics.get("videoCount") or 0)

        videos = _fetch_recent_videos(uploads_id, api_key, video_limit) if uploads_id else []
        valid_videos = [video for video in videos if video.get("title") and video.get("title") != "Private video"]

        parts = [
            (
                f"Public YouTube verine gore {channel_title} kanalinda "
                f"{_format_int(subscribers)} abone, {_format_int(total_views)} toplam goruntulenme "
                f"ve {_format_int(video_count)} video var."
            )
        ]
        if display_handle:
            parts.append(f"Kanal referansi: {display_handle}.")

        if valid_videos:
            avg_views = round(_average([video.get("views", 0) for video in valid_videos]))
            avg_likes = round(_average([video.get("likes", 0) for video in valid_videos]))
            avg_comments = round(_average([video.get("comments", 0) for video in valid_videos]))
            parts.append(
                f"Son {len(valid_videos)} videonun ortalamasi {_format_int(avg_views)} izlenme, "
                f"{_format_int(avg_likes)} begeni ve {_format_int(avg_comments)} yorum."
            )

            best_video = max(valid_videos, key=lambda item: item.get("views", 0))
            best_age = _days_ago_text(best_video.get("published_at", ""))
            best_duration = _format_duration(best_video.get("duration", ""))
            best_tail = []
            if best_age:
                best_tail.append(best_age)
            if best_duration:
                best_tail.append(best_duration)
            parts.append(
                f"En guclu son video '{best_video.get('title', 'Video')}' "
                f"- {_format_int(best_video.get('views', 0))} izlenme"
                + (f" ({', '.join(best_tail)})" if best_tail else "")
                + "."
            )

            publish_dates = [
                _parse_dt(video.get("published_at", ""))
                for video in valid_videos
            ]
            publish_dates = [value for value in publish_dates if value]
            if len(publish_dates) >= 2:
                gaps = []
                for earlier, later in zip(publish_dates[1:], publish_dates[:-1]):
                    delta = later - earlier
                    gaps.append(max(0.0, delta.total_seconds() / 86400))
                if gaps:
                    avg_gap = sum(gaps) / len(gaps)
                    parts.append(f"Yayin tempon son videolarda ortalama {avg_gap:.1f} gunde bir.")

            trend = _trend_sentence(valid_videos)
            if trend:
                parts.append(trend)

            query_l = str(query or "").lower()
            if any(word in query_l for word in ("detay", "analiz", "rapor", "son video", "son videolar")):
                recent_lines = []
                for index, video in enumerate(valid_videos[: min(3, len(valid_videos))], start=1):
                    tail = _days_ago_text(video.get("published_at", ""))
                    recent_lines.append(
                        f"{index}. {video.get('title', 'Video')} - "
                        f"{_format_int(video.get('views', 0))} izlenme, "
                        f"{_format_int(video.get('likes', 0))} begeni, "
                        f"{_format_int(video.get('comments', 0))} yorum"
                        + (f" ({tail})" if tail else "")
                    )
                if recent_lines:
                    parts.append("Son video detayi: " + " | ".join(recent_lines) + ".")

        parts.append(
            "Not: Studio erisimi olmadan izlenme suresi, CTR, gosterim, gelir ve trafik kaynagi verilerini goremem."
        )
        return " ".join(parts)
    except Exception as exc:
        return f"YouTube istatistikleri alinamadi: {exc}"
