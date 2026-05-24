"""
WhatsApp mesaj gönderme — macOS'ta WhatsApp Desktop veya Web üzerinden çalışır.
Alp Ünlü tarafından yapılmıştır — @alppunlu

Desteklenen akışlar:
- WhatsApp Desktop URL scheme ile numaraya sohbet açma
- WhatsApp Desktop içinde kişi adına göre sohbet arama
- WhatsApp Web üzerinden telefon numarasıyla taslak açma
- Sık kullanılan kişileri kalıcı belleğe kaydetme

Not:
- Otomatik gönderim ve kişi arama için macOS Accessibility izni gerekebilir.
"""

from __future__ import annotations

import json
import re
import subprocess
import unicodedata
import urllib.parse
from pathlib import Path

from memory.memory_manager import load_memory, update_memory


PREFERRED_BROWSERS = ["Google Chrome", "Safari"]
AUTO_SEND_DELAY_SECONDS = 2.4
BASE_DIR = Path(__file__).resolve().parent.parent
PHONEBOOK_FILE = BASE_DIR / "memory" / "phone_book.json"


def _normalize_phone(phone_number: str) -> str:
    digits = re.sub(r"\D+", "", phone_number or "")
    if len(digits) == 11 and digits.startswith("0"):
        digits = "90" + digits[1:]
    elif len(digits) == 10:
        digits = "90" + digits
    if len(digits) < 8 or len(digits) > 15:
        raise ValueError(
            "Telefon numarası uluslararası formatta olmalı. "
            "Örn: +905551112233"
        )
    return digits


def _normalize_lookup(text: str) -> str:
    text = (text or "").strip().casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("ı", "i")
    text = re.sub(r"\s+", " ", text)
    return text


def _contact_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _normalize_lookup(name)).strip("_") or "contact"


def _load_contacts() -> dict:
    memory = load_memory()
    contacts = memory.get("whatsapp_contacts", {})
    return contacts if isinstance(contacts, dict) else {}


def _load_phone_book() -> dict:
    try:
        if PHONEBOOK_FILE.exists():
            return json.loads(PHONEBOOK_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_phone_book(phone_book: dict):
    PHONEBOOK_FILE.parent.mkdir(parents=True, exist_ok=True)
    PHONEBOOK_FILE.write_text(
        json.dumps(phone_book, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _contact_candidates() -> list[dict]:
    candidates = []
    for source_name, source in (("whatsapp", _load_contacts()), ("phone_book", _load_phone_book())):
        if not isinstance(source, dict):
            continue
        for key, entry in source.items():
            if not isinstance(entry, dict):
                continue
            item = dict(entry)
            item.setdefault("display_name", key)
            item["_source"] = source_name
            item["_key"] = key
            candidates.append(item)
    return candidates


def _match_score(needle: str, candidate: str) -> int:
    candidate_norm = _normalize_lookup(candidate)
    if not candidate_norm:
        return 0
    if candidate_norm == needle:
        return 300
    if candidate_norm.startswith(needle) or needle.startswith(candidate_norm):
        return 220
    if needle in candidate_norm:
        return 160
    needle_parts = needle.split()
    if needle_parts and all(part in candidate_norm for part in needle_parts):
        return 120
    return 0


def _find_contact(recipient_name: str) -> dict | None:
    needle = _normalize_lookup(recipient_name)
    if not needle:
        return None

    best_match = None
    best_score = 0
    for entry in _contact_candidates():
        names = [entry.get("display_name", ""), entry.get("_key", "")]
        aliases = entry.get("aliases", [])
        if isinstance(aliases, list):
            names.extend(str(alias) for alias in aliases)
        elif aliases:
            names.append(str(aliases))

        for name in names:
            score = _match_score(needle, name)
            if score > best_score:
                best_score = score
                best_match = entry

    return best_match


def save_whatsapp_contact(display_name: str, phone_number: str, aliases: str = "") -> str:
    if not display_name or not display_name.strip():
        return "Kişi adı boş olamaz."

    try:
        normalized_phone = _normalize_phone(phone_number)
    except ValueError as exc:
        return str(exc)

    alias_list = []
    if aliases and aliases.strip():
        alias_list = [part.strip() for part in aliases.split(",") if part.strip()]

    key = _contact_key(display_name)
    update_memory(
        {
            "whatsapp_contacts": {
                key: {
                    "value": f"+{normalized_phone}",
                    "display_name": display_name.strip(),
                    "aliases": alias_list,
                }
            }
        }
    )

    if alias_list:
        return f"{display_name.strip()} WhatsApp kişilerine kaydedildi. Takma adlar: {', '.join(alias_list)}"
    return f"{display_name.strip()} WhatsApp kişilerine kaydedildi."


def _unfold_vcf_lines(text: str) -> list[str]:
    unfolded = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r\n")
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def import_phone_book_from_vcf(vcf_path: str) -> str:
    source = Path(vcf_path).expanduser()
    if not source.exists():
        return f"Rehber dosyası bulunamadı: {source}"

    try:
        text = source.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return f"Rehber dosyası okunamadı: {exc}"

    entries = {}
    current_lines = []
    imported = 0
    skipped = 0

    def _flush_card(lines: list[str]):
        nonlocal imported, skipped
        if not lines:
            return
        display_name = ""
        aliases = []
        numbers = []
        for line in lines:
            upper = line.upper()
            if upper.startswith("FN:"):
                display_name = line.split(":", 1)[1].strip()
            elif upper.startswith("N:") and not display_name:
                parts = [part.strip() for part in line.split(":", 1)[1].split(";") if part.strip()]
                if parts:
                    display_name = " ".join(reversed(parts[:2])).strip()
            elif "TEL" in upper and ":" in line:
                number = line.split(":", 1)[1].strip()
                if number:
                    numbers.append(number)

        if not display_name or not numbers:
            skipped += 1
            return

        normalized_numbers = []
        for raw_number in numbers:
            try:
                normalized_numbers.append("+" + _normalize_phone(raw_number))
            except ValueError:
                continue
        if not normalized_numbers:
            skipped += 1
            return

        if " " in display_name:
            aliases.extend(part for part in display_name.split() if len(part) > 1)
        key = _contact_key(display_name)
        entries[key] = {
            "display_name": display_name,
            "value": normalized_numbers[0],
            "numbers": normalized_numbers,
            "aliases": sorted({alias for alias in aliases if _normalize_lookup(alias) != _normalize_lookup(display_name)}),
            "source": "vcf_import",
        }
        imported += 1

    for line in _unfold_vcf_lines(text):
        if line.upper() == "BEGIN:VCARD":
            current_lines = []
        elif line.upper() == "END:VCARD":
            _flush_card(current_lines)
            current_lines = []
        else:
            current_lines.append(line)

    phone_book = _load_phone_book()
    phone_book.update(entries)
    _save_phone_book(phone_book)
    return f"{imported} rehber kişisi içe aktarıldı, {skipped} kayıt atlandı."


def _copy_to_clipboard(text: str) -> None:
    subprocess.run(["pbcopy"], input=text, text=True, check=True, timeout=5)


def _run_osascript(script: str, timeout: int = 18) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        return False, f"AppleScript çalıştırılamadı: {exc}"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() or "Bilinmeyen AppleScript hatası"
        return False, detail

    return True, (result.stdout or "").strip()


def _open_in_browser(url: str) -> str:
    for app_name in PREFERRED_BROWSERS:
        result = subprocess.run(
            ["open", "-a", app_name, url],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return app_name

    subprocess.run(["open", url], check=False, timeout=10)
    return "default browser"


def _auto_send_with_osascript(app_name: str) -> tuple[bool, str]:
    script = (
        f'delay {AUTO_SEND_DELAY_SECONDS}\n'
        f'tell application "{app_name}" to activate\n'
        "delay 0.3\n"
        'tell application "System Events"\n'
        "    key code 36\n"
        "end tell\n"
    )
    return _run_osascript(script, timeout=12)


def _open_whatsapp_desktop_via_scheme(phone_number: str, message: str) -> tuple[bool, str]:
    encoded_message = urllib.parse.quote(message.strip())
    url = f"whatsapp://send?phone={phone_number}&text={encoded_message}"
    try:
        result = subprocess.run(
            ["open", url],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        return False, f"WhatsApp Desktop açılamadı: {exc}"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() or "WhatsApp URL scheme açılamadı."
        return False, detail

    return True, "WhatsApp Desktop sohbeti açıldı."


def _open_whatsapp_desktop_by_name(recipient_name: str, message: str, send_now: bool) -> tuple[bool, str]:
    try:
        subprocess.run(["open", "-a", "WhatsApp"], check=True, timeout=10)
        _copy_to_clipboard(recipient_name.strip())
    except Exception as exc:
        return False, f"WhatsApp Desktop açılamadı: {exc}"

    search_script = (
        'tell application "WhatsApp" to activate\n'
        "delay 1.1\n"
        'tell application "System Events"\n'
        '    keystroke "f" using {command down}\n'
        "    delay 0.3\n"
        '    keystroke "a" using {command down}\n'
        "    delay 0.1\n"
        '    keystroke "v" using {command down}\n'
        "    delay 1.0\n"
        "    key code 36\n"
        "end tell\n"
    )
    ok, detail = _run_osascript(search_script, timeout=14)
    if not ok:
        return False, detail

    try:
        _copy_to_clipboard(message.strip())
    except Exception as exc:
        return False, f"Mesaj panoya kopyalanamadı: {exc}"

    send_line = "    key code 36\n" if send_now else ""
    message_script = (
        "delay 0.7\n"
        'tell application "WhatsApp" to activate\n'
        "delay 0.2\n"
        'tell application "System Events"\n'
        '    keystroke "v" using {command down}\n'
        "    delay 0.3\n"
        f"{send_line}"
        "end tell\n"
    )
    ok, detail = _run_osascript(message_script, timeout=14)
    if not ok:
        return False, detail

    if send_now:
        return True, f"WhatsApp Desktop üzerinden {recipient_name.strip()} kişisine mesaj gönderildi."
    return True, f"WhatsApp Desktop üzerinden {recipient_name.strip()} için taslak mesaj açıldı."


def _open_whatsapp_web(phone_number: str, message: str) -> tuple[bool, str]:
    encoded_message = urllib.parse.quote(message.strip())
    url = f"https://web.whatsapp.com/send?phone={phone_number}&text={encoded_message}"
    try:
        app_name = _open_in_browser(url)
    except Exception as exc:
        return False, f"WhatsApp Web açılamadı: {exc}"
    return True, app_name


def send_whatsapp_message(
    message: str,
    phone_number: str = "",
    recipient_name: str = "",
    send_now: bool = False,
    app_target: str = "auto",
) -> str:
    if not message or not message.strip():
        return "Mesaj boş olamaz."

    app_target = (app_target or "auto").strip().lower()
    if app_target not in {"auto", "desktop", "web"}:
        app_target = "auto"

    normalized_phone = ""
    if phone_number and phone_number.strip():
        try:
            normalized_phone = _normalize_phone(phone_number)
        except ValueError as exc:
            return str(exc)

    resolved_name = recipient_name.strip() if recipient_name else ""
    contact = _find_contact(resolved_name) if resolved_name else None

    if contact and not normalized_phone:
        stored_phone = str(contact.get("value", "")).strip()
        try:
            normalized_phone = _normalize_phone(stored_phone)
        except ValueError:
            normalized_phone = ""
        resolved_name = str(contact.get("display_name", resolved_name)).strip() or resolved_name
        contact_source = contact.get("_source", "")
    else:
        contact_source = ""

    if resolved_name and normalized_phone and (contact is None or contact.get("_source") == "phone_book"):
        # Bir kullanıcı numarayla birlikte isim verdiyse bunu sık kullanılanlara ekle.
        alias_list = contact.get("aliases", []) if isinstance(contact, dict) else []
        aliases = ", ".join(str(alias) for alias in alias_list) if alias_list else ""
        save_whatsapp_contact(resolved_name, normalized_phone, aliases=aliases)

    if app_target in {"auto", "desktop"}:
        if normalized_phone:
            ok, detail = _open_whatsapp_desktop_via_scheme(normalized_phone, message)
            if ok:
                source_note = " (rehberden bulundu)" if contact_source == "phone_book" else ""
                if not send_now:
                    label = resolved_name or f"+{normalized_phone}"
                    return f"WhatsApp Desktop içinde {label}{source_note} için taslak mesaj açıldı."
                ok_send, send_detail = _auto_send_with_osascript("WhatsApp")
                if ok_send:
                    label = resolved_name or f"+{normalized_phone}"
                    return f"WhatsApp Desktop üzerinden {label}{source_note} kişisine mesaj gönderildi."
                return (
                    "WhatsApp Desktop sohbeti açıldı ama otomatik gönderim tamamlanamadı. "
                    f"{send_detail}. Sistem Ayarları > Gizlilik ve Güvenlik > Erişilebilirlik izni gerekebilir."
                )
            if app_target == "desktop" and not resolved_name:
                return f"WhatsApp Desktop açılırken hata oldu: {detail}"

        if resolved_name:
            ok, detail = _open_whatsapp_desktop_by_name(resolved_name, message, send_now)
            if ok:
                return detail
            if app_target == "desktop":
                return (
                    "WhatsApp Desktop kişi adına göre açılırken hata oldu. "
                    f"{detail}. Erişilebilirlik izni ve WhatsApp içindeki kişi adı eşleşmesi gerekli olabilir."
                )

    if not normalized_phone:
        if resolved_name:
            return (
                f"'{resolved_name}' için kayıtlı bir telefon numarası bulamadım ve Desktop araması da tamamlanamadı. "
                "İstersen önce kişiyi numarasıyla kaydet."
            )
        return "WhatsApp mesajı için kişi adı veya telefon numarası gerekli."

    ok, detail = _open_whatsapp_web(normalized_phone, message)
    if not ok:
        return detail

    if not send_now:
        source_note = " (rehberden bulundu)" if contact_source == "phone_book" else ""
        return (
            f"WhatsApp sohbeti {detail} içinde {resolved_name or f'+{normalized_phone}'}{source_note} için taslak mesajla açıldı. "
            "Göndermek için Enter'a bas."
        )

    ok_send, send_detail = _auto_send_with_osascript(detail if detail in PREFERRED_BROWSERS else "Google Chrome")
    if ok_send:
        label = resolved_name or f"+{normalized_phone}"
        source_note = " (rehberden bulundu)" if contact_source == "phone_book" else ""
        return f"WhatsApp Web üzerinden {label}{source_note} kişisine mesaj gönderildi."

    return (
        "WhatsApp Web sohbeti açıldı ama otomatik gönderim tamamlanamadı. "
        f"{send_detail}. Sistem Ayarları > Gizlilik ve Güvenlik > Erişilebilirlik izni gerekebilir."
    )
