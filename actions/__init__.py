"""
JARVIS Actions — Güvenlik-hardened PC kontrol modülleri.

Her modül bağımsız olarak kullanılabilir.
"""

from .open_app import open_app
from .sys_info import get_system_info
from .browser import browser_control
from .shell import shell_run
from .weather import get_weather
from .health import get_health_score
from .media import open_youtube_search, open_spotify_search
from .screen_vision import analyze_screen
from .tts import speak, get_available_voices, get_tts_info

__all__ = [
    "open_app",
    "get_system_info",
    "browser_control",
    "shell_run",
    "get_weather",
    "get_health_score",
    "open_youtube_search",
    "open_spotify_search",
    "analyze_screen",
    "speak",
    "get_available_voices",
    "get_tts_info",
]
