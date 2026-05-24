"""
Apple Reminders tools for JARVIS.
Alp Ünlü tarafından yapılmıştır — @alppunlu

Reads reminder lists and creates new reminders through the shared
EventKit helper app used by calendar access.
"""

from __future__ import annotations

import datetime as dt
import json
import re

from actions.calendar import _run_helper


TR_WEEKDAYS = ["Pazartesi", "Sali", "Carsamba", "Persembe", "Cuma", "Cumartesi", "Pazar"]
TR_MONTHS = ["", "Ocak", "Subat", "Mart", "Nisan", "Mayis", "Haziran", "Temmuz", "Agustos", "Eylul", "Ekim", "Kasim", "Aralik"]


def _normalize_query(query: str) -> tuple[str, int]:
    q = (query or "").strip().lower()
    if any(token in q for token in ("bugun", "today")):
        return "today", 8
    if any(token in q for token in ("geciken", "gecmis", "overdue")):
        return "overdue", 8
    if any(token in q for token in ("siradaki", "sıradaki", "next")):
        return "next", 1
    if any(token in q for token in ("hepsi", "tum", "tüm", "all", "listele")):
        return "all", 10
    return "upcoming", 8


def _parse_payload(raw: str) -> tuple[bool, str, list[dict]]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return False, "Gecersiz animsatici yaniti alindi.", []

    if not isinstance(payload, dict):
        return False, "Animsatici verisi beklenen formatta degil.", []

    if not payload.get("ok", False):
        return False, str(payload.get("detail") or payload.get("error") or "Animsatici erisimi basarisiz."), []

    reminders = payload.get("reminders", [])
    if not isinstance(reminders, list):
        return False, "Animsatici listesi okunamadi.", []

    normalized: list[dict] = []
    for item in reminders:
        if not isinstance(item, dict):
            continue
        try:
            due_ts = int(item.get("due_ts", 0) or 0)
            priority = int(item.get("priority", 0) or 0)
        except (TypeError, ValueError):
            continue
        normalized.append(
            {
                "title": str(item.get("title", "")).strip() or "Adsiz animsatici",
                "list_name": str(item.get("list_name", "")).strip(),
                "notes": str(item.get("notes", "")).strip(),
                "completed": bool(item.get("completed", False)),
                "priority": priority,
                "due_ts": due_ts,
                "all_day": bool(item.get("all_day", False)),
            }
        )

    normalized.sort(key=lambda item: (item["due_ts"] <= 0, item["due_ts"] or 0, item["title"].lower()))
    return True, "", normalized


def _parse_created_payload(raw: str) -> tuple[bool, str, dict]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return False, "Gecersiz animsatici yaniti alindi.", {}

    if not isinstance(payload, dict):
        return False, "Animsatici verisi beklenen formatta degil.", {}

    if not payload.get("ok", False):
        return False, str(payload.get("detail") or payload.get("error") or "Animsatici eklenemedi."), {}

    created = payload.get("created", {})
    if not isinstance(created, dict):
        return False, "Animsatici kaydi okunamadi.", {}

    try:
        due_ts = int(created.get("due_ts", 0) or 0)
        priority = int(created.get("priority", 0) or 0)
    except (TypeError, ValueError):
        due_ts = 0
        priority = 0

    return True, "", {
        "title": str(created.get("title", "")).strip() or "Adsiz animsatici",
        "list_name": str(created.get("list_name", "")).strip(),
        "notes": str(created.get("notes", "")).strip(),
        "priority": priority,
        "due_ts": due_ts,
        "all_day": bool(created.get("all_day", False)),
    }


def _day_label(when: dt.datetime, now: dt.datetime) -> str:
    today = now.date()
    target = when.date()
    if target == today:
        return "bugun"
    if target == today + dt.timedelta(days=1):
        return "yarin"
    return f"{when.day} {TR_MONTHS[when.month]} {TR_WEEKDAYS[when.weekday()]}"


def _format_due(item: dict, now: dt.datetime) -> str:
    if item["due_ts"] <= 0:
        return "zaman atanmamis"
    due = dt.datetime.fromtimestamp(item["due_ts"])
    if item["all_day"]:
        return f"{_day_label(due, now)} tum gun"
    return f"{_day_label(due, now)} {due.strftime('%H:%M')}"


def _format_reminder_line(item: dict, now: dt.datetime) -> str:
    parts = [f"{_format_due(item, now)} - {item['title']}"]
    if item["list_name"]:
        parts.append(f"[{item['list_name']}]")
    if item["priority"] == 1:
        parts.append("(yuksek oncelik)")
    return " ".join(parts)


def _permission_message() -> str:
    return (
        "Animsatici erisim izni gerekiyor. "
        "Ilk denemede macOS izin penceresi gelirse onayla; gelmediyse "
        "Sistem Ayarlari > Gizlilik ve Guvenlik > Animsaticilar bolumunde "
        "'JARVIS Calendar Helper' uygulamasina izin ver."
    )


def get_reminders(query: str = "upcoming", limit: int = 8, list_name: str = "") -> str:
    mode, default_limit = _normalize_query(query)
    limit = max(1, min(20, int(limit or default_limit)))
    ok, raw = _run_helper(
        "reminders_list",
        payload={"query": mode, "limit": limit, "list_name": (list_name or "").strip()},
        timeout=25,
    )
    if not ok:
        detail = raw.lower()
        if "permission_denied" in detail or "not authorized" in detail or "mach error 4099" in detail:
            return _permission_message()
        return f"Animsaticilar okunamadi: {raw}"

    parsed_ok, detail, reminders = _parse_payload(raw)
    if not parsed_ok:
        low = detail.lower()
        if "permission" in low or "mach error 4099" in low:
            return _permission_message()
        return f"Animsaticilar okunamadi: {detail}"

    if not reminders:
        if mode == "today":
            return "Bugun icin animsatici gorunmuyor."
        if mode == "overdue":
            return "Geciken animsatici gorunmuyor."
        if mode == "next":
            return "Siradaki animsaticiyi bulamadim."
        if mode == "all":
            return "Kayitli acik animsatici gorunmuyor."
        return "Yaklasan animsatici gorunmuyor."

    now = dt.datetime.now()
    if mode == "next":
        return f"Siradaki animsatici: {_format_reminder_line(reminders[0], now)}."

    if mode == "today":
        header = f"Bugun icin {len(reminders)} animsatici buldum:"
    elif mode == "overdue":
        header = f"Gecikmis {len(reminders)} animsatici buldum:"
    elif mode == "all":
        header = f"Acik {len(reminders)} animsatici buldum:"
    else:
        header = f"Yaklasan {len(reminders)} animsatici buldum:"

    lines = [header]
    for item in reminders:
        lines.append(f"- {_format_reminder_line(item, now)}")
    return "\n".join(lines)


def _normalize_due_iso(due_iso: str) -> tuple[str, bool]:
    raw = (due_iso or "").strip()
    if not raw:
        return "", False

    candidates = (
        ("%Y-%m-%dT%H:%M:%S", False),
        ("%Y-%m-%dT%H:%M", False),
        ("%Y-%m-%d %H:%M:%S", False),
        ("%Y-%m-%d %H:%M", False),
        ("%d.%m.%Y %H:%M", False),
        ("%Y-%m-%d", True),
        ("%d.%m.%Y", True),
    )

    if raw.endswith("Z"):
        try:
            parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return parsed.isoformat(), False
        except ValueError:
            pass

    if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", raw):
        try:
            parsed = dt.datetime.fromisoformat(raw)
            return parsed.isoformat(timespec="minutes"), False
        except ValueError:
            pass

    for fmt, is_all_day in candidates:
        try:
            parsed = dt.datetime.strptime(raw, fmt)
            if is_all_day:
                return parsed.date().isoformat(), True
            return parsed.isoformat(timespec="minutes"), False
        except ValueError:
            continue

    raise ValueError(
        "Animsatici tarihi gecersiz. due_iso icin 'YYYY-MM-DD' veya 'YYYY-MM-DDTHH:MM' kullan."
    )


def add_reminder(
    title: str,
    due_iso: str = "",
    notes: str = "",
    list_name: str = "",
    priority: str = "",
    all_day: bool = False,
) -> str:
    if not title or not title.strip():
        return "Animsatici basligi bos olamaz."

    normalized_due = ""
    normalized_all_day = bool(all_day)
    if due_iso and due_iso.strip():
        try:
            normalized_due, inferred_all_day = _normalize_due_iso(due_iso)
        except ValueError as exc:
            return str(exc)
        normalized_all_day = normalized_all_day or inferred_all_day

    ok, raw = _run_helper(
        "create_reminder",
        payload={
            "title": title.strip(),
            "due_iso": normalized_due,
            "notes": (notes or "").strip(),
            "list_name": (list_name or "").strip(),
            "priority": (priority or "").strip(),
            "all_day": normalized_all_day,
        },
        timeout=25,
    )
    if not ok:
        detail = raw.lower()
        if "permission_denied" in detail or "not authorized" in detail or "mach error 4099" in detail:
            return _permission_message()
        return f"Animsatici eklenemedi: {raw}"

    parsed_ok, detail, created = _parse_created_payload(raw)
    if not parsed_ok:
        low = detail.lower()
        if "permission" in low or "mach error 4099" in low:
            return _permission_message()
        return f"Animsatici eklenemedi: {detail}"

    now = dt.datetime.now()
    when = _format_due(created, now)
    list_suffix = f" [{created['list_name']}]" if created["list_name"] else ""
    return f"Animsatici eklendi: {when} - {created['title']}{list_suffix}"
