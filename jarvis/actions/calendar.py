"""
Apple Calendar okuma araci.
Alp Ünlü tarafından yapılmıştır — @alppunlu

Takvim verisini macOS EventKit uzerinden Swift yardimiyla okur.
Bu yol AppleScript'e gore daha stabil ve tarih filtrelemesi daha sagliklidir.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
SWIFT_CACHE_DIR = BASE_DIR / ".swift-cache"
HELPERS_DIR = BASE_DIR / "helpers"
HELPER_SOURCE = HELPERS_DIR / "jarvis_calendar_helper.swift"
HELPER_PLIST = HELPERS_DIR / "jarvis_calendar_helper.plist"
HELPER_APP = HELPERS_DIR / "JARVIS Calendar Helper.app"
HELPER_CONTENTS_DIR = HELPER_APP / "Contents"
HELPER_MACOS_DIR = HELPER_CONTENTS_DIR / "MacOS"
HELPER_RESOURCES_DIR = HELPER_CONTENTS_DIR / "Resources"
HELPER_INFO_PLIST = HELPER_CONTENTS_DIR / "Info.plist"
HELPER_BIN = HELPER_MACOS_DIR / "jarvis-calendar-helper"

TR_WEEKDAYS = ["Pazartesi", "Sali", "Carsamba", "Persembe", "Cuma", "Cumartesi", "Pazar"]
TR_MONTHS = ["", "Ocak", "Subat", "Mart", "Nisan", "Mayis", "Haziran", "Temmuz", "Agustos", "Eylul", "Ekim", "Kasim", "Aralik"]


def _month_start(value: dt.datetime) -> dt.datetime:
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _add_months(value: dt.datetime, months: int) -> dt.datetime:
    total = (value.year * 12 + (value.month - 1)) + months
    year = total // 12
    month = total % 12 + 1
    return value.replace(year=year, month=month, day=1)


def _range_payload(start: dt.datetime, end: dt.datetime) -> dict:
    return {
        "start_iso": start.isoformat(),
        "end_iso": end.isoformat(),
    }


def _normalize_query(query: str) -> dict:
    q = (query or "today").strip().lower()
    now = dt.datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    month_match = re.search(r"(\d+)\s*(ay|month|months)", q)
    if "gelecek ay" in q or "önümüzdeki ay" in q or "onumuzdeki ay" in q or "next month" in q:
        start = _add_months(_month_start(now), 1)
        end = _add_months(start, 1)
        return {
            "helper_mode": "range",
            "payload": _range_payload(start, end),
            "default_limit": 24,
            "kind": "next_month",
            "header": "Gelecek ay icin {count} etkinlik buldum:",
            "empty": "Gelecek ay takviminde etkinlik gorunmuyor.",
        }
    if "bu ay" in q or "this month" in q:
        start = _month_start(now)
        end = _add_months(start, 1)
        return {
            "helper_mode": "range",
            "payload": _range_payload(start, end),
            "default_limit": 24,
            "kind": "this_month",
            "header": "Bu ay icin {count} etkinlik buldum:",
            "empty": "Bu ay takviminde etkinlik gorunmuyor.",
        }
    if month_match:
        months = max(1, min(12, int(month_match.group(1))))
        start = today_start
        end = _add_months(_month_start(now), months)
        return {
            "helper_mode": "range",
            "payload": _range_payload(start, end),
            "default_limit": min(60, max(12, months * 12)),
            "kind": "months",
            "header": f"Onumuzdeki {months} ay icin {{count}} etkinlik buldum:",
            "empty": f"Onumuzdeki {months} ayda takviminde etkinlik gorunmuyor.",
        }

    week_match = re.search(r"(\d+)\s*(hafta|week|weeks)", q)
    if week_match:
        weeks = max(1, min(12, int(week_match.group(1))))
        start = today_start
        end = today_start + dt.timedelta(days=weeks * 7)
        return {
            "helper_mode": "range",
            "payload": _range_payload(start, end),
            "default_limit": min(60, max(8, weeks * 8)),
            "kind": "weeks",
            "header": f"Onumuzdeki {weeks} hafta icin {{count}} etkinlik buldum:",
            "empty": f"Onumuzdeki {weeks} haftada takviminde etkinlik gorunmuyor.",
        }

    day_match = re.search(r"(\d+)\s*(g[uü]n|gun|day|days)", q)
    if day_match:
        days = max(1, min(365, int(day_match.group(1))))
        start = today_start
        end = today_start + dt.timedelta(days=days)
        return {
            "helper_mode": "range",
            "payload": _range_payload(start, end),
            "default_limit": min(60, max(8, days * 2)),
            "kind": "days",
            "header": f"Onumuzdeki {days} gun icin {{count}} etkinlik buldum:",
            "empty": f"Onumuzdeki {days} gunde takviminde etkinlik gorunmuyor.",
        }

    if any(token in q for token in ("yarin", "tomorrow")):
        return {
            "helper_mode": "tomorrow",
            "payload": None,
            "default_limit": 6,
            "kind": "tomorrow",
            "header": "Yarin icin {count} etkinlik buldum:",
            "empty": "Yarin takviminde etkinlik gorunmuyor.",
        }
    if any(token in q for token in ("hafta", "week", "7 gun")):
        return {
            "helper_mode": "week",
            "payload": None,
            "default_limit": 10,
            "kind": "week",
            "header": "Onumuzdeki 7 gun icin {count} etkinlik buldum:",
            "empty": "Onumuzdeki 7 gunde takviminde etkinlik gorunmuyor.",
        }
    if any(token in q for token in ("siradaki", "sıradaki", "sonraki", "next")):
        return {
            "helper_mode": "next",
            "payload": None,
            "default_limit": 1,
            "kind": "next",
            "header": "",
            "empty": "Siradaki takvim etkinligini bulamadim.",
        }
    if any(token in q for token in ("ajanda", "agenda", "yaklasan", "yaklaşan", "upcoming")):
        return {
            "helper_mode": "agenda",
            "payload": None,
            "default_limit": 8,
            "kind": "agenda",
            "header": "Yaklasan ajandanda {count} etkinlik var:",
            "empty": "Yaklasan takvim etkinligi gorunmuyor.",
        }
    return {
        "helper_mode": "today",
        "payload": None,
        "default_limit": 6,
        "kind": "today",
        "header": "Bugun icin {count} etkinlik buldum:",
        "empty": "Bugun takviminde etkinlik gorunmuyor.",
    }


def _ensure_helper_binary() -> tuple[bool, str]:
    SWIFT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    HELPER_MACOS_DIR.mkdir(parents=True, exist_ok=True)
    HELPER_RESOURCES_DIR.mkdir(parents=True, exist_ok=True)

    if not HELPER_SOURCE.exists():
        return False, "Takvim helper kaynak dosyasi bulunamadi."
    if not HELPER_PLIST.exists():
        return False, "Takvim helper plist dosyasi bulunamadi."

    source_mtime = max(HELPER_SOURCE.stat().st_mtime, HELPER_PLIST.stat().st_mtime)
    if (
        HELPER_BIN.exists()
        and HELPER_INFO_PLIST.exists()
        and HELPER_BIN.stat().st_mtime >= source_mtime
        and HELPER_INFO_PLIST.stat().st_mtime >= source_mtime
    ):
        return True, ""

    try:
        HELPER_INFO_PLIST.write_text(HELPER_PLIST.read_text(encoding="utf-8"), encoding="utf-8")
        env = os.environ.copy()
        env["CLANG_MODULE_CACHE_PATH"] = str(SWIFT_CACHE_DIR)
        env["SWIFT_MODULE_CACHE_PATH"] = str(SWIFT_CACHE_DIR)
        result = subprocess.run(
            [
                "swiftc",
                str(HELPER_SOURCE),
                "-o",
                str(HELPER_BIN),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
    except FileNotFoundError:
        return False, "swiftc bulunamadi."
    except subprocess.TimeoutExpired:
        return False, "Takvim helper binary derlenirken zaman asimina ugradi."
    except Exception as exc:
        return False, f"Takvim helper binary derlenemedi: {exc}"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return False, detail or "Swift helper binary derlenemedi."

    try:
        HELPER_BIN.chmod(0o755)
    except Exception:
        pass

    return True, ""


def _run_helper(mode: str, payload: dict | None = None, timeout: int = 20) -> tuple[bool, str]:
    ok, detail = _ensure_helper_binary()
    if not ok:
        return False, detail

    output_path = None
    payload_path = None
    raw = ""
    try:
        handle = tempfile.NamedTemporaryFile(prefix="jarvis-calendar-", suffix=".json", delete=False)
        output_path = Path(handle.name)
        handle.close()
        helper_args = [mode]
        if payload is not None:
            payload_handle = tempfile.NamedTemporaryFile(prefix="jarvis-helper-payload-", suffix=".json", delete=False)
            payload_path = Path(payload_handle.name)
            payload_handle.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            payload_handle.close()
            helper_args.append(str(payload_path))
        helper_args.append(str(output_path))
        result = subprocess.run(
            ["open", "-W", "-n", str(HELPER_APP), "--args", *helper_args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, "Organizer helper istegi zaman asimina ugradi."
    except Exception as exc:
        return False, f"Organizer helper calistirilamadi: {exc}"

    if output_path and output_path.exists():
        try:
            raw = output_path.read_text(encoding="utf-8").strip()
        except Exception:
            raw = ""

    final_raw = raw or (result.stdout or "").strip()
    if result.returncode != 0:
        final_raw = raw

    if not final_raw:
        try:
            helper_args = [mode]
            if payload is not None and payload_path:
                helper_args.append(str(payload_path))
            if output_path:
                helper_args.append(str(output_path))
            result = subprocess.run(
                [str(HELPER_BIN), *helper_args],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if output_path and output_path.exists():
                try:
                    final_raw = output_path.read_text(encoding="utf-8").strip()
                except Exception:
                    final_raw = ""
            if not final_raw and result.returncode == 0:
                final_raw = (result.stdout or "").strip()
            if result.returncode != 0 and not final_raw:
                detail = (result.stderr or result.stdout or "").strip()
                return False, detail or "Organizer helper calismadi."
        except subprocess.TimeoutExpired:
            return False, "Organizer helper istegi zaman asimina ugradi."
        except Exception as exc:
            return False, f"Organizer helper calistirilamadi: {exc}"
    try:
        if output_path and output_path.exists():
            output_path.unlink()
    except Exception:
        pass
    try:
        if payload_path and payload_path.exists():
            payload_path.unlink()
    except Exception:
        pass

    return True, final_raw


def _parse_payload(raw: str) -> tuple[bool, str, list[dict]]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return False, "Gecersiz takvim yaniti alindi.", []

    if not isinstance(payload, dict):
        return False, "Takvim verisi beklenen formatta degil.", []

    if not payload.get("ok", False):
        return False, str(payload.get("detail") or payload.get("error") or "Takvim erisimi basarisiz."), []

    events = payload.get("events", [])
    if not isinstance(events, list):
        return False, "Takvim olaylari okunamadi.", []

    normalized: list[dict] = []
    for item in events:
        if not isinstance(item, dict):
            continue
        try:
            start_ts = int(item.get("start_ts", 0))
            end_ts = int(item.get("end_ts", 0))
        except (TypeError, ValueError):
            continue
        if start_ts <= 0 or end_ts <= 0:
            continue
        normalized.append(
            {
                "start_ts": start_ts,
                "end_ts": end_ts,
                "calendar": str(item.get("calendar", "")).strip(),
                "title": str(item.get("title", "")).strip() or "Adsiz etkinlik",
                "location": str(item.get("location", "")).strip(),
                "all_day": bool(item.get("all_day", False)),
            }
        )

    normalized.sort(key=lambda event: (event["start_ts"], event["title"].lower()))
    return True, "", normalized


def _parse_single_event_payload(raw: str) -> tuple[bool, str, dict | None]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return False, "Gecersiz takvim yaniti alindi.", None

    if not isinstance(payload, dict):
        return False, "Takvim verisi beklenen formatta degil.", None

    if not payload.get("ok", False):
        return False, str(payload.get("detail") or payload.get("error") or "Takvim islemi basarisiz."), None

    item = payload.get("created")
    if not isinstance(item, dict):
        return False, "Olusturulan etkinlik bilgisi alinamadi.", None

    try:
        start_ts = int(item.get("start_ts", 0))
        end_ts = int(item.get("end_ts", 0))
    except (TypeError, ValueError):
        return False, "Olusturulan etkinlik zamani okunamadi.", None

    if start_ts <= 0 or end_ts <= 0:
        return False, "Olusturulan etkinlik zamani gecersiz.", None

    return True, "", {
        "start_ts": start_ts,
        "end_ts": end_ts,
        "calendar": str(item.get("calendar", "")).strip(),
        "title": str(item.get("title", "")).strip() or "Adsiz etkinlik",
        "location": str(item.get("location", "")).strip(),
        "all_day": bool(item.get("all_day", False)),
    }


def _parse_deleted_event_payload(raw: str) -> tuple[bool, str, dict | None]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return False, "Gecersiz takvim yaniti alindi.", None

    if not isinstance(payload, dict):
        return False, "Takvim verisi beklenen formatta degil.", None

    if not payload.get("ok", False):
        detail = str(payload.get("detail") or payload.get("error") or "Takvim silme islemi basarisiz.")
        matches = payload.get("matches")
        if isinstance(matches, list) and matches:
            preview = []
            now = dt.datetime.now()
            for item in matches[:3]:
                if not isinstance(item, dict):
                    continue
                try:
                    event = {
                        "start_ts": int(item.get("start_ts", 0)),
                        "end_ts": int(item.get("end_ts", 0)),
                        "calendar": str(item.get("calendar", "")).strip(),
                        "title": str(item.get("title", "")).strip() or "Adsiz etkinlik",
                        "location": str(item.get("location", "")).strip(),
                        "all_day": bool(item.get("all_day", False)),
                    }
                except (TypeError, ValueError):
                    continue
                if event["start_ts"] > 0 and event["end_ts"] > 0:
                    preview.append(_format_event_line(event, now))
            if preview:
                detail += " Eslesen etkinlikler: " + " | ".join(preview)
        return False, detail, None

    item = payload.get("deleted")
    if not isinstance(item, dict):
        return False, "Silinen etkinlik bilgisi alinamadi.", None

    try:
        start_ts = int(item.get("start_ts", 0))
        end_ts = int(item.get("end_ts", 0))
    except (TypeError, ValueError):
        return False, "Silinen etkinlik zamani okunamadi.", None

    if start_ts <= 0 or end_ts <= 0:
        return False, "Silinen etkinlik zamani gecersiz.", None

    return True, "", {
        "start_ts": start_ts,
        "end_ts": end_ts,
        "calendar": str(item.get("calendar", "")).strip(),
        "title": str(item.get("title", "")).strip() or "Adsiz etkinlik",
        "location": str(item.get("location", "")).strip(),
        "all_day": bool(item.get("all_day", False)),
    }


def _calendar_permission_message() -> str:
    return (
        "Takvim erisim izni gerekiyor. "
        "Ilk denemede macOS izin penceresi gelirse onayla; gelmediyse "
        "Sistem Ayarlari > Gizlilik ve Guvenlik > Takvim bolumunde "
        "'JARVIS Calendar Helper' uygulamasini ara ve izin ver."
    )


def _day_label(when: dt.datetime, now: dt.datetime) -> str:
    today = now.date()
    target = when.date()
    if target == today:
        return "bugun"
    if target == today + dt.timedelta(days=1):
        return "yarin"
    return f"{when.day} {TR_MONTHS[when.month]} {TR_WEEKDAYS[when.weekday()]}"


def _format_time_range(event: dict, now: dt.datetime) -> str:
    start = dt.datetime.fromtimestamp(event["start_ts"])
    end = dt.datetime.fromtimestamp(event["end_ts"])
    prefix = _day_label(start, now)
    if event["all_day"]:
        return f"{prefix} tum gun"
    return f"{prefix} {start.strftime('%H:%M')}-{end.strftime('%H:%M')}"


def _format_event_line(event: dict, now: dt.datetime) -> str:
    pieces = [f"{_format_time_range(event, now)} - {event['title']}"]
    if event["calendar"]:
        pieces.append(f"[{event['calendar']}]")
    if event["location"]:
        pieces.append(f"@ {event['location']}")
    return " ".join(pieces)


def get_calendar_events(query: str = "today", limit: int = 6) -> str:
    window = _normalize_query(query)
    limit = max(1, min(60, int(limit or window["default_limit"])))

    ok, raw = _run_helper(
        window["helper_mode"],
        payload=window.get("payload"),
        timeout=20,
    )
    if not ok:
        detail = raw.lower()
        if "permission_denied" in detail or "not authorized" in detail or "mach error 4099" in detail:
            return _calendar_permission_message()
        return f"Takvim okunamadi: {raw}"

    parsed_ok, detail, events = _parse_payload(raw)
    if not parsed_ok:
        low = detail.lower()
        if "permission" in low or "mach error 4099" in low:
            return _calendar_permission_message()
        return f"Takvim okunamadi: {detail}"

    now = dt.datetime.now()
    if window["kind"] in {"next", "agenda"}:
        events = [event for event in events if event["end_ts"] >= int(now.timestamp())]

    if not events:
        return window["empty"]

    if window["kind"] == "next":
        return f"Siradaki etkinlik: {_format_event_line(events[0], now)}."

    selected = events[:limit]
    header = str(window["header"]).format(count=len(selected))

    lines = [header]
    for event in selected:
        lines.append(f"- {_format_event_line(event, now)}")
    return "\n".join(lines)


def add_calendar_event(
    title: str,
    start_iso: str,
    end_iso: str = "",
    notes: str = "",
    location: str = "",
    calendar_name: str = "",
    all_day: bool = False,
) -> str:
    title = (title or "").strip()
    start_iso = (start_iso or "").strip()
    if not title:
        return "Takvime eklemek icin etkinlik basligi gerekli."
    if not start_iso:
        return "Takvime eklemek icin baslangic tarihi gerekli."

    payload = {
        "title": title,
        "start_iso": start_iso,
        "end_iso": (end_iso or "").strip(),
        "notes": (notes or "").strip(),
        "location": (location or "").strip(),
        "calendar_name": (calendar_name or "").strip(),
        "all_day": bool(all_day),
    }

    ok, raw = _run_helper("create_event", payload=payload, timeout=25)
    if not ok:
        detail = raw.lower()
        if "permission_denied" in detail or "not authorized" in detail or "mach error 4099" in detail:
            return _calendar_permission_message()
        return f"Takvim etkinligi eklenemedi: {raw}"

    parsed_ok, detail, event = _parse_single_event_payload(raw)
    if not parsed_ok:
        low = detail.lower()
        if "permission" in low or "mach error 4099" in low:
            return _calendar_permission_message()
        return f"Takvim etkinligi eklenemedi: {detail}"

    assert event is not None
    now = dt.datetime.now()
    line = _format_event_line(event, now)
    return f"Takvime eklendi: {line}."


def delete_calendar_event(
    title: str,
    start_iso: str = "",
    calendar_name: str = "",
    delete_all_matches: bool = False,
) -> str:
    title = (title or "").strip()
    if not title:
        return "Takvimden silmek icin etkinlik basligi gerekli."

    payload = {
        "title": title,
        "start_iso": (start_iso or "").strip(),
        "calendar_name": (calendar_name or "").strip(),
        "delete_all_matches": bool(delete_all_matches),
    }

    ok, raw = _run_helper("delete_event", payload=payload, timeout=25)
    if not ok:
        detail = raw.lower()
        if "permission_denied" in detail or "not authorized" in detail or "mach error 4099" in detail:
            return _calendar_permission_message()
        return f"Takvim etkinligi silinemedi: {raw}"

    parsed_ok, detail, event = _parse_deleted_event_payload(raw)
    if not parsed_ok:
        low = detail.lower()
        if "permission" in low or "mach error 4099" in low:
            return _calendar_permission_message()
        return f"Takvim etkinligi silinemedi: {detail}"

    assert event is not None
    now = dt.datetime.now()
    line = _format_event_line(event, now)
    return f"Takvimden silindi: {line}."
