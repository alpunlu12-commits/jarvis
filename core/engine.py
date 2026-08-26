"""JARVIS lokal karar motoru — regex/keyword tabanlı intent parsing.

Hiçbir API çağırmaz. Gelen Türkçe metni parse edip
tool name + args + confidence score döndürür.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    """Parsed komut sonucu."""
    intent: str
    args: dict[str, str | bool] = field(default_factory=dict)
    confidence: float = 0.0
    raw: str = ""


# ---------------------------------------------------------------------------
# Yardımcı fonksiyonlar
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    result = text.strip().lower()
    for tr, asc in [
        ("ı", "i"), ("İ", "i"), ("ş", "s"), ("Ş", "s"), ("ğ", "g"), ("Ğ", "g"),
        ("ü", "u"), ("Ü", "u"), ("ö", "o"), ("Ö", "o"), ("ç", "s"), ("Ç", "s"),
    ]:
        result = result.replace(tr, asc)
    import unicodedata
    result = "".join(c for c in unicodedata.normalize("NFD", result) if unicodedata.category(c) != "Mn")
    result = re.sub(r"[^\w\s']", " ", result)
    result = re.sub(r"\s+", " ", result).strip()
    result = result.replace("j", "c").replace("z", "c")
    return result


def _contains(text: str, *keywords: str) -> bool:
    """Metin içinde herhangi bir keyword var mı? Keyword'leri de normalize eder."""
    return any(_normalize(kw) in text for kw in keywords)


def _contains_word(text: str, word: str) -> bool:
    """Kelime olarak tam eşleşme (partial match önler)."""
    return bool(re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text))


def _extract_after(text: str, *triggers: str) -> str:
    """Trigger sonrası kalan metni döndürür."""
    for trigger in triggers:
        idx = text.find(trigger)
        if idx != -1:
            return text[idx + len(trigger):].strip()
    return ""


def _extract_location(text: str) -> str:
    """Konum bilgisini metinden çıkarır."""
    match = re.search(r"(\w+(?:'?\w+)?)\s*(?:da|de)\s+hava", text)
    if match:
        return match.group(1).strip("'")
    match = re.search(r"hava\s+(?:durumu|nasil)\s+(\w+)", text)
    if match:
        return match.group(1)
    match = re.search(r"(\w+)\s+hava\s+durumu", text)
    if match:
        return match.group(1)
    return ""


def _extract_app_name(text: str) -> str:
    """Uygulama adını çıkarır: 'spotify'i ac' → 'Spotify'"""
    match = re.search(
        r"([\w']+(?:'?[\w']*)?)\s*(?:'?i|'?i|'?u|'?u)?\s+(?:ac|as)",
        text,
    )
    if match:
        app = match.group(1).strip()
        return app.title()
    return ""


def _extract_media_query(text: str) -> str:
    """Medya sorgusunu çıkarır: 'spotify da the weeknd cal' → 'the weeknd'"""
    match = re.search(
        r"(?:youtube|spotify|apple\s*music|music)\s*(?:'\w+)?\s+(.+?)\s+(?:ac|as|cal|oynat)",
        text,
    )
    if match:
        return match.group(1).strip()
    return _extract_after(text, "ac", "as", "cal", "oynat")


def _extract_whatsapp_info(text: str) -> dict[str, str]:
    """WhatsApp alıcı ve mesajını çıkarır."""
    result: dict[str, str] = {}
    match = re.search(
        r"(\w+(?:'?\w+)?)\s*(?:'?ya|'?ye)?\s+whatsapp(?:'\w+)?\s+(?:mesaj\s+)?(?:gonder|hazirla|yolla)",
        text,
    )
    if match:
        result["recipient_name"] = match.group(1).strip("'")
    msg_match = re.search(
        r"mesaj\s+(?:gonder|hazirla|yolla)\s+(.+)",
        text,
    )
    if msg_match:
        result["message"] = msg_match.group(1).strip()
    return result


# ---------------------------------------------------------------------------
# Yasaklı shell komutları
# ---------------------------------------------------------------------------

_BLOCKED_SHELL_CMDS: set[str] = {
    "rm -rf", "format", "del /s", "shutdown", "restart", "reboot",
    "mkfs", "dd if=", "> /dev/", "cipher /w", "wevtutil cl",
}


# ---------------------------------------------------------------------------
# Ana parsing fonksiyonu
# ---------------------------------------------------------------------------

def parse_command(text: str) -> ParsedCommand:
    """Türkçe metni parse edip ParsedCommand döndürür.

    Her intent için confidence skoru hesaplanır.
    Bilinmeyen komutlarda intent='chat' döner.
    """
    if not text or not text.strip():
        return ParsedCommand(intent="chat", args={}, confidence=0.0, raw=text)

    n = _normalize(text)

    # --- selamla (en yüksek öncelik) ---
    if _contains(n, "merhaba", "selam", "hey", "selamlar", "gunaydin", "iyi gunler", "iyi aksamlar"):
        return ParsedCommand(intent="selamla", args={}, confidence=0.95, raw=text)

    # --- delete_memory (unut/kaldır en çabuk eşleşen olsun) ---
    if _contains(n, "hafizadan sil", "unut", "kaldir", "bunu sil"):
        match_text = _extract_after(n, "hafizadan sil", "unut", "kaldir", "bunu sil")
        return ParsedCommand(
            intent="delete_memory", args={"match_text": match_text},
            confidence=0.85, raw=text,
        )

    # --- set_voice (erkek/kadin ses degisimi) ---
    if _contains(n, "erkek ses", "ahmet ses", "ahmet'e gec", "ahmete gec", "erkek yap") or ("erkek" in n and "ses" in n):
        return ParsedCommand(intent="set_voice", args={"voice": "ahmet"}, confidence=0.95, raw=text)
    if _contains(n, "kadin ses", "emel ses", "emele gec", "kadin yap") or ("kadin" in n and "ses" in n):
        return ParsedCommand(intent="set_voice", args={"voice": "emel"}, confidence=0.95, raw=text)
    if _contains(n, "ses degistir", "sesi degistir", "diger ses"):
        return ParsedCommand(intent="set_voice", args={"voice": "toggle"}, confidence=0.85, raw=text)

    # --- save_memory (hatırla / hatirlat ayrımı için kelime sınırı) ---
    if _contains(n, "hafizaya kaydet", "bunu hatirla") or (
        _contains(n, "hatirla", "kaydet") and not _contains(n, "hatirlat")
    ):
        content = _extract_after(n, "hafizaya kaydet", "hatirla", "bunu hatirla")
        return ParsedCommand(
            intent="save_memory", args={"content": content},
            confidence=0.80, raw=text,
        )

    # --- send_whatsapp_message ---
    if _contains(n, "whatsapp"):
        info = _extract_whatsapp_info(n)
        send_now = _contains(n, "gonder", "yolla")
        args_wa: dict[str, str | bool] = {"send_now": send_now}
        args_wa.update(info)
        return ParsedCommand(
            intent="send_whatsapp_message", args=args_wa,
            confidence=0.85, raw=text,
        )

    if _contains(n, "ayarlar", "yarlar", "ayalar", "settings"):
        if "ac" in n or "ayar" in n or "yar" in n:
            return ParsedCommand(
                intent="chat",
                args={"response": "AYARLAR altta ortada — AYARLAR butonuna tikla. Oradan mikrofon ve telefon QR'i yonetirsin.", "query": text},
                confidence=0.85, raw=text,
            )

    # --- play_media / youtube (open_app'ten once: "YouTube'dan X ac" media) ---
    if _contains(n, "youtube", "spotify", "apple music", "muzik"):
        is_youtube = "youtube" in n
        if is_youtube:
            media_query = _extract_media_query(n)
            return ParsedCommand(
                intent="browser_control",
                args={"query": media_query, "action": "play_youtube"},
                confidence=0.80, raw=text,
            )
        media_query = _extract_media_query(n)
        if media_query:
            return ParsedCommand(
                intent="play_media",
                args={"query": media_query, "action": "play"},
                confidence=0.80, raw=text,
            )

    # --- open_app (bir uygulama adı + "aç" kalıbı varsa) ---
    app_name = _extract_app_name(n)
    if app_name and _contains(n, "ac", "as", "baslat", "calistir"):
        return ParsedCommand(
            intent="open_app", args={"app_name": app_name},
            confidence=0.90, raw=text,
        )

    # --- sys_info ---
    if _contains(n, "pil", "cpu", "ram", "bellek", "disk", "saat"):
        info_type = "general"
        if "pil" in n:
            info_type = "battery"
        elif "saat" in n:
            info_type = "time"
        elif "cpu" in n:
            info_type = "cpu"
        elif "ram" in n or "bellek" in n:
            info_type = "ram"
        elif "disk" in n:
            info_type = "disk"
        return ParsedCommand(
            intent="sys_info", args={"info_type": info_type},
            confidence=0.85, raw=text,
        )

    # --- get_weather ---
    location = _extract_location(n)
    if _contains(n, "hava", "sicaklik", "derece"):
        args: dict[str, str | bool] = {}
        if location:
            args["location"] = location.title()
        return ParsedCommand(
            intent="get_weather", args=args,
            confidence=0.80 if location else 0.60, raw=text,
        )

    # --- add_reminder ---
    if _contains(n, "animsatici", "hatirlat", "reminder"):
        title = _extract_after(n, "hatirlat", "animsatici ekle")
        return ParsedCommand(
            intent="add_reminder", args={"title": title},
            confidence=0.75, raw=text,
        )

    # --- add_calendar_event ---
    if _contains(n, "takvime ekle", "ajandaya ekle", "etkinlik ekle", "randevu ekle"):
        title = _extract_after(n, "takvime ekle", "ajandaya ekle", "etkinlik ekle", "randevu ekle")
        return ParsedCommand(
            intent="add_calendar_event", args={"title": title},
            confidence=0.75, raw=text,
        )

    # --- delete_calendar_event ---
    if _contains(n, "takvimden sil", "ajandadan sil"):
        title = _extract_after(n, "takvimden sil", "ajandadan sil")
        return ParsedCommand(
            intent="delete_calendar_event", args={"title": title},
            confidence=0.75, raw=text,
        )

    # --- get_calendar_events ---
    if _contains(n, "takvim", "ajanda", "etkinlik", "randevu"):
        query = "all"
        if "bugun" in n:
            query = "today"
        elif "yarin" in n:
            query = "tomorrow"
        elif "bu hafta" in n:
            query = "this_week"
        return ParsedCommand(
            intent="get_calendar_events", args={"query": query},
            confidence=0.70, raw=text,
        )

    # --- analyze_screen ---
    if _contains(n, "ekran", "pencere", "ekran goruntusu", "ekran analiz"):
        return ParsedCommand(
            intent="analyze_screen",
            args={"query": text, "target": "active_window"},
            confidence=0.75, raw=text,
        )

    # --- browser_control ---
    if _contains(n, "google", "tarayici", "web"):
        query = _extract_after(n, "google", "tarayici")
        return ParsedCommand(
            intent="browser_control",
            args={"action": "search", "query": query},
            confidence=0.70, raw=text,
        )

    # --- shell_run ---
    if _contains(n, "terminal", "shell", "komut calistir", "komutu calistir"):
        for blocked in _BLOCKED_SHELL_CMDS:
            if blocked in n:
                return ParsedCommand(
                    intent="chat",
                    args={"response": f"Bu komut guvenli degil: {blocked}"},
                    confidence=0.90, raw=text,
                )
        cmd = _extract_after(n, "calistir", "shell'de", "terminalde", "terminalde calistir")
        return ParsedCommand(
            intent="shell_run", args={"command": cmd},
            confidence=0.70, raw=text,
        )

    # --- Bilinmeyen → chat (echo DEĞİL - yardım) ---
    hints = []
    if len(n) < 30:
        hints.append(f"'{text}' ne demek istedin? Örn: 'saat kaç', 'spotify aç', 'hava nasıl', 'hesap makinesi aç'")
    else:
        hints.append("Anlayamadım — daha kısa komut dene: 'saat kaç', 'ram ne durumda', 'not al: ...'")
    return ParsedCommand(
        intent="chat", args={"response": hints[0], "query": text},
        confidence=0.30, raw=text,
    )
