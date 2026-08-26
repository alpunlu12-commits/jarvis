"""Kalıcı bellek — JSON dosyasına kaydedilir.

Atomic write (temp + rename), max 500 entry limiti, normalize/tokenize.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MEMORY_FILE = BASE_DIR / "memory" / "memory.json"
MAX_ENTRIES = 500

# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_memory() -> dict[str, object]:
    """Memory dosyasını okur; hata/dosya yoksa boş dict döndürür."""
    if not MEMORY_FILE.exists():
        return {}
    try:
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------

def _write_memory(mem: dict[str, object]) -> None:
    """Atomic write: temp dosyasına yaz, sonra rename ile değiştir."""
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd: int | None = None
    tmp_path: str = ""
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(MEMORY_FILE.parent),
            suffix=".tmp",
        )
        tmp_fd = fd
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(mem, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        # Windows: hedef varsa önce sil
        if MEMORY_FILE.exists():
            MEMORY_FILE.unlink()
        os.rename(tmp_path, str(MEMORY_FILE))
    except OSError:
        # Fallback: basit yaz
        try:
            MEMORY_FILE.write_text(
                json.dumps(mem, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass
        # temp dosyasını temizle
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Entry counting & pruning
# ---------------------------------------------------------------------------

def _count_entries(mem: dict[str, object]) -> int:
    """Toplam entry sayısını sayar (deep count)."""
    count = 0
    for value in mem.values():
        if isinstance(value, dict):
            count += len(value)
        else:
            count += 1
    return count


def _prune_if_needed(mem: dict[str, object]) -> bool:
    """Entry sayısı MAX_ENTRIES'i aşarsa en eski kayıtları siler."""
    if _count_entries(mem) <= MAX_ENTRIES:
        return False
    # Dict entry'lerini sil (en azemplokeyacious category'den başla)
    for cat in list(mem.keys()):
        bucket = mem[cat]
        if isinstance(bucket, dict):
            # Dict items'ları aged sırayla sil
            keys_to_remove = list(bucket.keys())
            excess = _count_entries(mem) - MAX_ENTRIES
            if excess <= 0:
                break
            for key in keys_to_remove[:excess]:
                del bucket[key]
                excess -= 1
            if not bucket:
                del mem[cat]
        else:
            if _count_entries(mem) <= MAX_ENTRIES:
                break
            del mem[cat]
    return True


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

def update_memory(data: dict[str, object]) -> dict[str, object]:
    """Memory'yi günceller, max limit kontrolü yapar, sonucu döndürür."""
    mem = load_memory()
    _deep_merge(mem, data)
    _prune_if_needed(mem)
    _write_memory(mem)
    return mem


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_memory(
    category: str = "",
    key: str = "",
    match_text: str = "",
) -> str:
    """Memory'den kayit siler."""
    mem = load_memory()
    if not mem:
        return "Hafızada silinecek bir kayıt yok."

    category = (category or "").strip()
    key = (key or "").strip()
    match_text = (match_text or "").strip()

    if category and key:
        bucket = mem.get(category)
        if isinstance(bucket, dict) and key in bucket:
            del bucket[key]
            if not bucket:
                mem.pop(category, None)
            _write_memory(mem)
            return f"{category}/{key} hafızadan kaldırıldı."
        return "Bu hafıza kaydını bulamadım."

    needle = _normalize_text(match_text or key)
    if not needle:
        return "Silmek için category/key veya match_text gerekli."

    for cat, bucket in list(mem.items()):
        if not isinstance(bucket, dict):
            if _entry_matches(needle, cat, cat, bucket):
                del mem[cat]
                _write_memory(mem)
                return f"{cat} hafızadan kaldırıldı."
            continue

        for item_key, item_value in list(bucket.items()):
            if _entry_matches(needle, cat, item_key, item_value):
                del bucket[item_key]
                if not bucket:
                    mem.pop(cat, None)
                _write_memory(mem)
                return f"{cat}/{item_key} hafızadan kaldırıldı."

    return "Eşleşen bir hafıza kaydı bulamadım."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deep_merge(base: dict[str, object], update: dict[str, object]) -> None:
    """Update dict'indeki değerleri base'e derinleştirir."""
    for k, v in update.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)  # type: ignore[arg-type]
        else:
            base[k] = v


def _normalize_text(text: str) -> str:
    """Unicode normalize + casefold + whitespace squeeze."""
    text = (text or "").strip().casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("ı", "i")
    return " ".join(text.split())


def _entry_value_text(value: object) -> str:
    """Entry value'sunu string'e çevir."""
    if isinstance(value, dict):
        base = value.get("value")
        if base is not None:
            return str(base)
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _tokenize_text(text: str) -> list[str]:
    """Metni normalize edip token'lara böler."""
    normalized = _normalize_text(text)
    return [token for token in re.split(r"[^a-z0-9]+", normalized) if token]


def _entry_matches(
    needle: str, category: str, item_key: str, item_value: object
) -> bool:
    """Entry'nin needle ile eşleşip eşleşmediğini kontrol eder."""
    haystacks = [
        _normalize_text(category),
        _normalize_text(item_key),
        _normalize_text(_entry_value_text(item_value)),
    ]
    if any(needle in hay for hay in haystacks):
        return True

    tokens = [tok for tok in _tokenize_text(needle) if len(tok) >= 3]
    if not tokens:
        return False

    entry_tokens: list[str] = []
    for hay in haystacks:
        entry_tokens.extend(_tokenize_text(hay))

    matched = 0
    for token in tokens:
        if any(token in et or et in token for et in entry_tokens):
            matched += 1

    if len(tokens) == 1:
        return matched == 1
    return matched >= min(2, len(tokens))


# ---------------------------------------------------------------------------
# Prompt formatlama
# ---------------------------------------------------------------------------

def format_memory_for_prompt(memory: dict[str, object]) -> str:
    """Memory'yi LLM prompt'una uygun string'e çevirir."""
    if not memory:
        return ""
    lines: list[str] = ["[KULLANICI HAKKINDA BİLGİLER]"]
    for category, items in memory.items():
        if isinstance(items, dict):
            for key, val in items.items():
                if category == "whatsapp_contacts" and isinstance(val, dict):
                    display_name = val.get("display_name", key)
                    value = val.get("value", "")
                    aliases = val.get("aliases", [])
                    alias_str = ""
                    if isinstance(aliases, list) and aliases:
                        alias_str = f" aliases={', '.join(str(a) for a in aliases)}"
                    lines.append(f"  {category}/{display_name}: {value}{alias_str}")
                else:
                    value = val.get("value", val) if isinstance(val, dict) else val
                    lines.append(f"  {category}/{key}: {value}")
        else:
            lines.append(f"  {category}: {items}")
    return "\n".join(lines)
