"""
JARVIS Voice — Lokal STT (Speech-to-Text) ve wake word algilama.

Moduller:
- listener: Konusma algilama + wake word ("jarvis")
"""

from .listener import VoiceListener

__all__ = ["VoiceListener"]
