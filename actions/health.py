"""
actions/health.py — disa aktarilan saglik verilerini okur.

Veri akisi:
  iPhone saglik disa aktarma verisi
  → iCloud Drive/Auto Export/JARVIS/HealthAutoExport-YYYY-MM-DD.json
  → JARVIS
"""

import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path

MOBILE_DOCS = Path.home() / "Library" / "Mobile Documents"

# Saglik disa aktarma verisinin iCloud container'i
HEALTH_DIR = MOBILE_DOCS / "iCloud~com~ifunography~HealthExport" / "Documents" / "JARVIS"

# Geriye dönük uyumluluk — eski konumlar
_LEGACY_DIRS = [
    MOBILE_DOCS / "com~apple~CloudDocs" / "Auto Export" / "JARVIS",
    MOBILE_DOCS / "com~apple~CloudDocs" / "JARVIS",
]

# Legacy düz dosya
_LEGACY_FILE = MOBILE_DOCS / "com~apple~CloudDocs" / "JARVIS" / "health_data.json"

STALE_WARN_MINUTES = 120  # 2 saatten eski veriye uyarı


def _normalize_query(text: str) -> str:
    text = (text or "").strip().lower()
    text = (
        text.replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
    )
    return text


def _extract_target_date(query: str) -> date | None:
    q = _normalize_query(query)
    today = date.today()

    if any(token in q for token in ("onceki gun", "evvelsi gun", "iki gun once")):
        return today - timedelta(days=2)
    if any(token in q for token in ("dun", "yesterday")):
        return today - timedelta(days=1)
    if any(token in q for token in ("bugun", "today", "simdi")):
        return today

    iso_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", q)
    if iso_match:
        try:
            return datetime.strptime(iso_match.group(1), "%Y-%m-%d").date()
        except ValueError:
            pass

    tr_match = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b", q)
    if tr_match:
        day_s, month_s, year_s = tr_match.groups()
        try:
            return date(int(year_s), int(month_s), int(day_s))
        except ValueError:
            pass

    return None


def _date_from_file(path: Path | None) -> date | None:
    if not path:
        return None
    match = re.search(r"HealthAutoExport-(\d{4}-\d{2}-\d{2})", path.name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def _find_health_file(target_date: date | None = None) -> Path | None:
    """
    En son HealthAutoExport-*.json dosyasını bulur.
    Önce asıl klasörü, bulamazsa legacy konumları dener.
    """
    search_dirs = [HEALTH_DIR] + _LEGACY_DIRS
    if target_date:
        target_name = f"HealthAutoExport-{target_date.isoformat()}.json"
        for directory in search_dirs:
            candidate = directory / target_name
            if candidate.exists():
                return candidate
    for directory in search_dirs:
        if not directory.exists():
            continue
        candidates = sorted(
            directory.glob("HealthAutoExport-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return candidates[0]
    return None


def _resolve_file(target_date: date | None = None) -> Path | None:
    """En güncel sağlık dosyasını döndürür. Yeni konum önce, legacy sonra."""
    latest_export = _find_health_file(target_date)
    if latest_export:
        return latest_export
    if _LEGACY_FILE.exists():
        return _LEGACY_FILE
    return None


# ── Yardımcı ─────────────────────────────────────────────────────────────────

def _age_str(ts: float) -> str:
    mins = (time.time() - ts) / 60
    if mins < 2:   return "az önce"
    if mins < 60:  return f"{int(mins)} dakika önce"
    hrs = mins / 60
    if hrs < 24:   return f"{hrs:.1f} saat önce"
    return f"{hrs/24:.1f} gün önce"


def _v(d: dict, key: str, unit: str = "", dec: int = 0) -> str:
    val = d.get(key)
    if val is None:
        return "—"
    try:
        f = float(val)
        return f"{f:.{dec}f}{unit}" if dec else f"{int(round(f))}{unit}"
    except (ValueError, TypeError):
        return str(val)


# ── Saglik export format parser ──────────────────────────────────────────────

def _parse_hae(raw: dict, target_date: date | None = None) -> dict:
    """
    Saglik export'un combined JSON formatini duz bir dict'e cevirir.
    Format: {"data": {"metrics": [{"name": "heart_rate", "data": [{"qty": 72, ...}]}]}}
    """
    out = {}

    metrics_list = (
        raw.get("data", {}).get("metrics")          # combined format
        or raw.get("metrics")                        # alternatif
        or []
    )

    def latest_qty(entries: list) -> float | None:
        """Listeden en son qty/value değerini al."""
        for entry in reversed(entries):
            for key in ("qty", "value", "Avg", "avg"):
                if key in entry:
                    try:
                        return float(entry[key])
                    except (ValueError, TypeError):
                        pass
        return None

    day_key = target_date.isoformat() if target_date else time.strftime("%Y-%m-%d")

    def today_sum(entries: list) -> float:
        """Hedef gündeki tüm kayıtları topla."""
        total = 0.0
        for e in entries:
            date_str = str(e.get("date", ""))
            if day_key in date_str:
                for key in ("qty", "value"):
                    if key in e:
                        try:
                            total += float(e[key])
                        except (ValueError, TypeError):
                            pass
        return total

    name_map = {
        # Export alani adi → bizim key'imiz
        "heart_rate":                  ("heart_rate",       "latest"),
        "resting_heart_rate":          ("resting_hr",       "latest"),
        "heart_rate_variability":      ("hrv",              "latest"),
        "heart_rate_variability_sdnn": ("hrv",              "latest"),
        "heartratevariabilitysdnn":    ("hrv",              "latest"),
        "blood_oxygen_saturation":     ("blood_oxygen_raw", "latest"),
        "oxygen_saturation":           ("blood_oxygen_raw", "latest"),
        "respiratory_rate":            ("respiratory_rate", "latest"),
        "step_count":                  ("steps",            "today_sum"),
        "steps":                       ("steps",            "today_sum"),
        "active_energy":               ("calories",         "today_sum"),
        "active_energy_burned":        ("calories",         "today_sum"),
        "basal_energy_burned":         ("basal_calories",   "today_sum"),
        "apple_exercise_time":         ("exercise_min",     "today_sum"),
        "exercise_time":               ("exercise_min",     "today_sum"),
        "exercise_minutes":            ("exercise_min",     "today_sum"),
        "apple_stand_hour":            ("stand_hours",      "today_sum"),
        "apple_stand_time":            ("stand_min",        "today_sum"),
        "time_in_daylight":            ("daylight_min",     "today_sum"),
        "flights_climbed":             ("flights_climbed",  "today_sum"),
        "walking_heart_rate_average":  ("walking_hr",       "latest"),
        "walking_speed":               ("walking_speed",    "latest"),
        "walking_asymmetry_percentage": ("walking_asymmetry_pct", "latest"),
        "walking_double_support_percentage": ("walking_double_support_pct", "latest"),
        "walking_step_length":         ("walking_step_length_cm", "latest"),
        "walking_running_distance":    ("walking_distance_km", "today_sum"),
        "environmental_audio_exposure": ("environment_audio_db", "latest"),
        "headphone_audio_exposure":    ("headphone_audio_db", "latest"),
        "physical_effort":             ("physical_effort",   "latest"),
        "sleep_analysis":              ("sleep_hours",      "latest"),
        "sleep_duration":              ("sleep_hours",      "latest"),
    }

    for metric in metrics_list:
        raw_name = metric.get("name", "").lower().replace(" ", "_")
        entries  = metric.get("data", [])
        if not entries:
            continue

        mapping = name_map.get(raw_name)
        if not mapping:
            continue
        our_key, mode = mapping

        if mode == "latest":
            val = latest_qty(entries)
        else:
            val = today_sum(entries)

        if val is not None:
            out[our_key] = val

    # Kan oksijeni: genellikle 0.0–1.0 arasında gelir, 0–100'e çevir
    if "blood_oxygen_raw" in out:
        raw_o2 = out.pop("blood_oxygen_raw")
        out["blood_oxygen"] = raw_o2 * 100 if raw_o2 <= 1.0 else raw_o2

    return out


def _load(target_date: date | None = None) -> tuple[dict, float, dict, date | None]:
    """JSON dosyasını yükle, (data_dict, timestamp, raw_json, hedef_tarih) döndür."""
    source_file = _resolve_file(target_date)
    if not source_file:
        raise FileNotFoundError("Sağlık dosyası bulunamadı.")

    raw = json.loads(source_file.read_text(encoding="utf-8"))
    file_mtime = source_file.stat().st_mtime
    source_date = _date_from_file(source_file) or target_date

    # Kendi basit formatımız mı?
    if "data" in raw and isinstance(raw["data"], dict) and "metrics" not in raw.get("data", {}):
        return raw["data"], raw.get("timestamp", file_mtime), raw, source_date

    # Export formati mi?
    if "data" in raw and "metrics" in raw.get("data", {}):
        return _parse_hae(raw, source_date), file_mtime, raw, source_date

    # Düz dict (eski basit format)
    return raw, file_mtime, raw, source_date


def _metrics_list(raw: dict) -> list:
    return raw.get("data", {}).get("metrics") or raw.get("metrics") or []


def _entry_datetime(entry: dict) -> datetime | None:
    raw_value = str(entry.get("date", "")).strip()
    if not raw_value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw_value, fmt)
        except ValueError:
            continue
    return None


def _entry_number(entry: dict, keys: tuple[str, ...] = ("qty", "value", "Avg", "avg", "Max", "max")) -> float | None:
    for key in keys:
        if key in entry:
            try:
                return float(entry[key])
            except (ValueError, TypeError):
                continue
    return None


def _entries_for_metric(raw: dict, names: tuple[str, ...], target_date: date | None = None) -> list[dict]:
    wanted = {name.lower().replace(" ", "_") for name in names}
    day_key = target_date.isoformat() if target_date else None
    matched = []
    for metric in _metrics_list(raw):
        raw_name = str(metric.get("name", "")).lower().replace(" ", "_")
        if raw_name not in wanted:
            continue
        for entry in metric.get("data", []) or []:
            if not day_key or day_key in str(entry.get("date", "")):
                matched.append(entry)
    return matched


def _float_or_none(data: dict, key: str) -> float | None:
    value = data.get(key)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _period_label(target_date: date | None) -> str:
    if not target_date:
        return "Seçili gün"
    if target_date == date.today():
        return "Bugün"
    if target_date == date.today() - timedelta(days=1):
        return "Dün"
    return target_date.strftime("%d %B %Y")


def _build_health_analysis(raw: dict, data: dict, query: str, target_date: date | None, age: str) -> str:
    period = _period_label(target_date)
    exercise_min = _float_or_none(data, "exercise_min") or 0.0
    calories = _float_or_none(data, "calories") or 0.0
    steps = _float_or_none(data, "steps") or 0.0
    distance = _float_or_none(data, "walking_distance_km") or 0.0
    walking_speed = _float_or_none(data, "walking_speed")
    hrv = _float_or_none(data, "hrv")
    resting_hr = _float_or_none(data, "resting_hr")
    current_hr = _float_or_none(data, "heart_rate")
    effort = _float_or_none(data, "physical_effort")

    exercise_entries = [
        e for e in _entries_for_metric(raw, ("apple_exercise_time", "exercise_time", "exercise_minutes"), target_date)
        if (_entry_number(e, ("qty", "value")) or 0) > 0
    ]
    heart_entries = _entries_for_metric(raw, ("heart_rate",), target_date)

    exercise_times = [dt for e in exercise_entries if (dt := _entry_datetime(e))]
    workout_window = ""
    if exercise_times:
        workout_window = f"{min(exercise_times).strftime('%H:%M')} - {max(exercise_times).strftime('%H:%M')}"

    peak_hr = None
    avg_hr_values = []
    for entry in heart_entries:
        peak_candidate = _entry_number(entry, ("Max", "qty", "value", "Avg", "avg"))
        avg_candidate = _entry_number(entry, ("Avg", "avg", "qty", "value"))
        if peak_candidate is not None:
            peak_hr = peak_candidate if peak_hr is None else max(peak_hr, peak_candidate)
        if avg_candidate is not None:
            avg_hr_values.append(avg_candidate)
    avg_hr = (sum(avg_hr_values) / len(avg_hr_values)) if avg_hr_values else None

    lines = []
    if any(k in _normalize_query(query) for k in ("antren", "antreman", "workout", "egzersiz", "spor", "fitness")):
        if exercise_min >= 10:
            lines.append(f"{period} için evet, belirgin bir antrenman/egzersiz kaydı var.")
        elif exercise_min > 0:
            lines.append(f"{period} için kısa süreli hareket kaydı var ama tam bir antrenman kadar güçlü görünmüyor.")
        else:
            lines.append(f"{period} için belirgin bir antrenman kaydı görünmüyor.")
    else:
        lines.append(f"{period} sağlık analizi hazır.")

    lines.append(f"Egzersiz süresi: {int(round(exercise_min))} dakika.")
    lines.append(f"Aktif kalori: {int(round(calories))} kcal, adım: {int(round(steps))}, mesafe: {distance:.2f} km.")
    if workout_window:
        lines.append(f"En net aktivite penceresi: {workout_window}.")
    if peak_hr is not None:
        hr_text = f"Pik nabız yaklaşık {int(round(peak_hr))} bpm"
        if avg_hr is not None:
            hr_text += f", günlük ortalama nabız yaklaşık {int(round(avg_hr))} bpm"
        lines.append(hr_text + ".")
    if walking_speed is not None:
        lines.append(f"Yürüme hızı yaklaşık {walking_speed:.1f} km/sa.")

    if exercise_min >= 60 or calories >= 600:
        lines.append("Yorum: yük oldukça yüksek, gün aktif geçmiş.")
    elif exercise_min >= 30 or calories >= 300:
        lines.append("Yorum: orta seviye, verimli bir aktivite günü.")
    elif steps >= 7000:
        lines.append("Yorum: belirgin bir yürüyüş/aktif yaşam günü.")
    else:
        lines.append("Yorum: yük hafif, daha çok günlük hareket düzeyinde.")

    recovery_notes = []
    if hrv is not None:
        if hrv >= 70:
            recovery_notes.append(f"HRV {hrv:.1f} ms ile iyi görünüyor")
        elif hrv >= 40:
            recovery_notes.append(f"HRV {hrv:.1f} ms ile orta seviyede")
        else:
            recovery_notes.append(f"HRV {hrv:.1f} ms ile düşük tarafta")
    if resting_hr is not None:
        recovery_notes.append(f"dinlenim nabzı {int(round(resting_hr))} bpm")
    elif current_hr is not None:
        recovery_notes.append(f"son nabız ölçümü {int(round(current_hr))} bpm")
    if recovery_notes:
        lines.append("Toparlanma: " + ", ".join(recovery_notes) + ".")

    if effort is not None:
        lines.append(f"Physical effort skoru yaklaşık {effort:.1f}.")

    lines.append(f"[güncelleme: {age}]")
    return "\n".join(lines)


# ── Formatlayıcı ─────────────────────────────────────────────────────────────

def _format(data: dict, query: str, age: str) -> str:
    q = query.lower()

    if any(k in q for k in ("nabız", "nabiz", "kalp", "heart", "bpm", "hrv")):
        return "\n".join([
            f"Anlık nabız    : {_v(data, 'heart_rate', ' bpm')}",
            f"Dinlenim nabzı : {_v(data, 'resting_hr', ' bpm')}",
            f"HRV            : {_v(data, 'hrv', ' ms', 1)}",
            f"Yürüyüş nabzı  : {_v(data, 'walking_hr', ' bpm')}",
            f"[güncelleme: {age}]",
        ])

    if any(k in q for k in ("adım", "step", "egzersiz", "exercise", "kalori", "aktivite", "activity", "kardiyo", "stand", "ayakta", "mesafe", "distance", "kat")):
        return "\n".join([
            f"Bugün adım     : {_v(data, 'steps')}",
            f"Aktif kalori   : {_v(data, 'calories', ' kcal')}",
            f"Bazal kalori   : {_v(data, 'basal_calories', ' kcal')}",
            f"Egzersiz süresi: {_v(data, 'exercise_min', ' dk')}",
            f"Ayakta saat    : {_v(data, 'stand_hours', ' saat')}",
            f"Ayakta süre    : {_v(data, 'stand_min', ' dk')}",
            f"Yürüme mesafesi: {_v(data, 'walking_distance_km', ' km', 2)}",
            f"Çıkılan kat    : {_v(data, 'flights_climbed')}",
            f"[güncelleme: {age}]",
        ])

    if any(k in q for k in ("yürüyüş", "yuruyus", "yürüme", "yurume", "walking", "mobility", "denge", "asimetri", "asymmetry", "hız", "hiz", "adım uzunluğu", "adim uzunlugu", "step length", "double support")):
        return "\n".join([
            f"Yürüme hızı    : {_v(data, 'walking_speed', ' km/sa', 1)}",
            f"Adım uzunluğu  : {_v(data, 'walking_step_length_cm', ' cm')}",
            f"Yürüyüş nabzı  : {_v(data, 'walking_hr', ' bpm')}",
            f"Asimetri       : {_v(data, 'walking_asymmetry_pct', '%', 1)}",
            f"Double support : {_v(data, 'walking_double_support_pct', '%', 1)}",
            f"Mesafe         : {_v(data, 'walking_distance_km', ' km', 2)}",
            f"[güncelleme: {age}]",
        ])

    if any(k in q for k in ("uyku", "sleep", "uyudum")):
        return "\n".join([
            f"Uyku süresi    : {_v(data, 'sleep_hours', ' saat', 1)}",
            f"Derin uyku     : {_v(data, 'deep_sleep_hours', ' saat', 1)}",
            f"REM uyku       : {_v(data, 'rem_sleep_hours', ' saat', 1)}",
            f"[güncelleme: {age}]",
        ])

    if any(k in q for k in ("oksijen", "spo2", "oxygen", "solunum")):
        return "\n".join([
            f"Kan oksijeni   : {_v(data, 'blood_oxygen', '%', 1)}",
            f"Solunum hızı   : {_v(data, 'respiratory_rate', ' nefes/dk', 1)}",
            f"[güncelleme: {age}]",
        ])

    if any(k in q for k in ("ses", "audio", "kulaklık", "kulaklik", "maruziyet", "gürültü", "gurultu", "desibel", "db", "headphone", "environmental")):
        return "\n".join([
            f"Çevresel ses   : {_v(data, 'environment_audio_db', ' dB', 1)}",
            f"Kulaklık sesi  : {_v(data, 'headphone_audio_db', ' dB', 1)}",
            f"[güncelleme: {age}]",
        ])

    if any(k in q for k in ("gün ışığı", "gun isigi", "daylight", "güneş", "gunes")):
        return "\n".join([
            f"Gün ışığı      : {_v(data, 'daylight_min', ' dk', 1)}",
            f"Physical effort: {_v(data, 'physical_effort', '', 1)}",
            f"[güncelleme: {age}]",
        ])

    return "\n".join([
        "── SAĞLIK ÖZETİ ──────────────────",
        f"💓 Nabız         : {_v(data, 'heart_rate', ' bpm')}  (din.: {_v(data, 'resting_hr', ' bpm')})",
        f"📊 HRV           : {_v(data, 'hrv', ' ms', 1)}",
        f"🚶 Yürüyüş nabzı : {_v(data, 'walking_hr', ' bpm')}",
        f"🩸 Kan oksijeni  : {_v(data, 'blood_oxygen', '%', 1)}",
        f"🫁 Solunum hızı  : {_v(data, 'respiratory_rate', ' nefes/dk', 1)}",
        f"👣 Adım          : {_v(data, 'steps')}",
        f"🔥 Aktif kalori  : {_v(data, 'calories', ' kcal')}",
        f"⚡ Bazal kalori  : {_v(data, 'basal_calories', ' kcal')}",
        f"🏃 Egzersiz      : {_v(data, 'exercise_min', ' dk')}",
        f"🧍 Stand         : {_v(data, 'stand_hours', ' saat')}  ({_v(data, 'stand_min', ' dk')})",
        f"🪜 Çıkılan kat   : {_v(data, 'flights_climbed')}",
        f"📏 Mesafe        : {_v(data, 'walking_distance_km', ' km', 2)}",
        f"🚀 Yürüme hızı   : {_v(data, 'walking_speed', ' km/sa', 1)}",
        f"📐 Adım uzunluğu : {_v(data, 'walking_step_length_cm', ' cm')}",
        f"🎧 Kulaklık sesi : {_v(data, 'headphone_audio_db', ' dB', 1)}",
        f"🌤 Gün ışığı     : {_v(data, 'daylight_min', ' dk', 1)}",
        f"💤 Uyku          : {_v(data, 'sleep_hours', ' saat', 1)}",
        f"──────────────────────────────────",
        f"[güncelleme: {age}]",
    ])


# ── Ana fonksiyon ─────────────────────────────────────────────────────────────

def get_health_data(query: str = "all") -> str:
    target_date = _extract_target_date(query)

    if not _resolve_file(target_date):
        return (
            "Sağlık verisi bulunamadı. "
            "iPhone'da desteklenen bir sağlık dışa aktarma aracı kurup "
            "iCloud Drive > Auto Export > JARVIS klasörüne export ayarlaman gerekiyor."
        )

    try:
        data, ts, raw, source_date = _load(target_date)
    except Exception as e:
        return f"Sağlık dosyası okunamadı: {e}"

    if not data:
        return "Sağlık dosyası boş veya tanınmayan formatta."

    age   = _age_str(ts)
    normalized_query = _normalize_query(query)
    if any(token in normalized_query for token in ("analiz", "yorum", "detay", "detayli", "antren", "antreman", "workout", "fitness", "dun", "yesterday")):
        result = _build_health_analysis(raw, data, query, source_date, age)
    else:
        result = _format(data, query, age)

    mins_old = (time.time() - ts) / 60
    if mins_old > STALE_WARN_MINUTES:
        result += f"\n⚠️  Veri {age} güncellendi — uygulamanın otomatik export ayarını kontrol et."

    return result


def get_welcome_health_summary() -> str:
    if not _resolve_file():
        return "Sağlık verilerin şu anda alınamadı."

    try:
        data, ts, _, _ = _load()
    except Exception:
        return "Sağlık verilerin şu anda alınamadı."

    if not data:
        return "Sağlık verilerin şu anda alınamadı."

    heart_rate = _v(data, "heart_rate", " bpm")
    steps = _v(data, "steps")
    exercise_min = _v(data, "exercise_min", " dakika")
    distance = _v(data, "walking_distance_km", " kilometre", 2)
    age = _age_str(ts)

    parts = []
    if heart_rate != "—":
        parts.append(f"Kalp atışın {heart_rate}")
    if exercise_min != "—":
        parts.append(f"bugün {exercise_min} kardiyo yaptın")
    if steps != "—":
        parts.append(f"{steps} adım attın")
    if distance != "—":
        parts.append(f"{distance} yürüdün")

    if not parts:
        return "Sağlık verilerin şu anda alınamadı."

    if len(parts) == 1:
        summary = parts[0] + "."
    else:
        summary = ", ".join(parts[:-1]) + f" ve {parts[-1]}."

    mins_old = (time.time() - ts) / 60
    if mins_old > STALE_WARN_MINUTES:
        summary += f" Sağlık verisi {age} güncellendi."

    return summary
