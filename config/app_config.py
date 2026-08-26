"""JARVIS yapılandırma yöneticisi — offline mod destekli."""

from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
CONFIG_PATH = CONFIG_DIR / "api_keys.json"

DEFAULT_CONFIG: dict[str, object] = {
    "gemini_api_key": "",
    "voice": "Charon",
    "tts_voice": "tr-TR-EmelNeural",
    "language": "tr",
    "offline_mode": True,
}


def load_app_config() -> dict[str, object]:
    """JSON config dosyasını okur; yoksa default'ları döndürür."""
    config = dict(DEFAULT_CONFIG)
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            config.update(raw)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return config


def save_app_config(updates: dict[str, object]) -> dict[str, object]:
    """Mevcut config'i updates ile birleştirip kaydeder."""
    config = load_app_config()
    for key, value in (updates or {}).items():
        if value is None:
            continue
        config[key] = value
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(config, indent=4, ensure_ascii=False),
        encoding="utf-8",
    )
    return config


def get_app_config_value(key: str, default: object = None) -> object:
    """Tek bir config değerini okur."""
    return load_app_config().get(key, default)


def has_gemini_api_key() -> bool:
    """Gemini API anahtarı tanımlı mı?"""
    value = str(get_app_config_value("gemini_api_key", "") or "").strip()
    return bool(value)


def is_offline_mode() -> bool:
    """Lokal mod aktif mi? API anahtarı yoksa otomatik True."""
    if not has_gemini_api_key():
        return True
    return bool(get_app_config_value("offline_mode", True))
