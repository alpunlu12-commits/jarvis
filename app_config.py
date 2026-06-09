# Alp Ünlü tarafından yapılmıştır — @alppunlu
from __future__ import annotations

import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
CONFIG_PATH = CONFIG_DIR / "api_keys.json"


DEFAULT_CONFIG = {
    "gemini_api_key": "",
    "voice": "Charon",
    "youtube_api_key": "",
    "youtube_channel_handle": "",
    "ai_provider": "gemini",
    "ollama_host": "http://127.0.0.1:11434",
    "ollama_model": "llama3",
    "stt_energy_threshold": 4000,
    "stt_pause_threshold": 2.0,
    "stt_phrase_threshold": 0.3,
    "stt_non_speaking_duration": 0.5,
}


def load_app_config() -> dict:
    config = dict(DEFAULT_CONFIG)
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            config.update(raw)
    except Exception:
        pass
    return config


def save_app_config(updates: dict) -> dict:
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


def get_app_config_value(key: str, default=None):
    return load_app_config().get(key, default)


def has_gemini_api_key() -> bool:
    provider = str(get_app_config_value("ai_provider", "gemini") or "gemini").strip()
    if provider == "ollama":
        return True
    value = str(get_app_config_value("gemini_api_key", "") or "").strip()
    return bool(value)
