"""
Medya oynatma — YouTube, Spotify Desktop ve Apple Music/Music uygulaması.
Alp Ünlü tarafından yapılmıştır — @alppunlu

Not:
- Spotify ve Music için otomatik oynatma best-effort yaklaşımıyla yapılır.
- Masaüstü uygulamalarında otomasyon için macOS Accessibility izni gerekebilir.
"""

from __future__ import annotations

import os
import subprocess
import urllib.parse

from actions.browser import browser_control


SPOTIFY_APP = "/Applications/Spotify.app"
MUSIC_APP = "/System/Applications/Music.app"


def _run_osascript(script: str, timeout: int = 16) -> tuple[bool, str]:
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


def _copy_to_clipboard(text: str) -> tuple[bool, str]:
    try:
        subprocess.run(["pbcopy"], input=text, text=True, check=True, timeout=5)
        return True, "ok"
    except Exception as exc:
        return False, f"Panoya kopyalanamadı: {exc}"


def _app_exists(path: str) -> bool:
    return os.path.exists(path)


def _play_youtube(query: str) -> str:
    return browser_control("play_youtube", query=query)


def _play_spotify(query: str, autoplay: bool = True) -> str:
    if not _app_exists(SPOTIFY_APP):
        return "Spotify yüklü görünmüyor."

    encoded_query = urllib.parse.quote(query.strip())
    search_url = f"spotify:search:{encoded_query}"

    try:
        subprocess.run(["open", search_url], check=True, timeout=10)
    except Exception as exc:
        return f"Spotify açılamadı: {exc}"

    if not autoplay:
        return f"Spotify içinde '{query}' araması açıldı."

    script = (
        'tell application "Spotify" to activate\n'
        "delay 1.8\n"
        'tell application "System Events"\n'
        "    key code 48\n"          # Tab
        "    delay 0.2\n"
        "    key code 125\n"         # Down
        "    delay 0.2\n"
        "    key code 36\n"          # Enter
        "    delay 0.5\n"
        "    key code 49\n"          # Space
        "end tell\n"
    )
    ok, detail = _run_osascript(script, timeout=14)
    if ok:
        return f"Spotify'da oynatılıyor: {query}"

    return (
        f"Spotify araması açıldı ama otomatik oynatma tamamlanamadı: {detail}. "
        "Erişilebilirlik izni gerekebilir."
    )


def _play_music_app(query: str, autoplay: bool = True) -> str:
    if not _app_exists(MUSIC_APP):
        return "Apple Music / Music uygulaması bulunamadı."

    if autoplay:
        escaped_query = query.replace("\\", "\\\\").replace('"', '\\"')
        script = (
            f'set queryText to "{escaped_query}"\n'
            'tell application "Music"\n'
            "    activate\n"
            "    try\n"
            "        set foundTracks to (search library playlist 1 for queryText only songs)\n"
            "        if (count of foundTracks) > 0 then\n"
            "            set targetTrack to item 1 of foundTracks\n"
            "            play targetTrack\n"
            "            return \"PLAYED\"\n"
            "        end if\n"
            "    end try\n"
            "end tell\n"
            "return \"NOT_FOUND\"\n"
        )
        ok, detail = _run_osascript(script, timeout=18)
        if ok and "PLAYED" in detail:
            return f"Music uygulamasında oynatılıyor: {query}"

    ok_clip, detail_clip = _copy_to_clipboard(query.strip())
    if not ok_clip:
        return detail_clip

    script = (
        'tell application "Music" to activate\n'
        "delay 1.0\n"
        'tell application "System Events"\n'
        '    keystroke "f" using {command down}\n'
        "    delay 0.3\n"
        '    keystroke "a" using {command down}\n'
        "    delay 0.1\n"
        '    keystroke "v" using {command down}\n'
        "    delay 1.1\n"
        "    key code 36\n"
        "    delay 0.7\n"
        "    key code 125\n"
        "    delay 0.2\n"
        "    key code 36\n"
        "end tell\n"
    )
    ok, detail = _run_osascript(script, timeout=16)
    if ok:
        if autoplay:
            return f"Music uygulamasında '{query}' için arama yapıldı ve ilk sonuç açıldı."
        return f"Music uygulamasında '{query}' araması açıldı."

    search_url = f"music://music.apple.com/search?term={urllib.parse.quote(query.strip())}"
    try:
        subprocess.run(["open", search_url], check=False, timeout=10)
    except Exception:
        pass
    return (
        f"Music uygulamasında doğrudan oynatma tamamlanamadı: {detail}. "
        f"Arama açıldı: {query}"
    )


def play_media(query: str, provider: str = "auto", autoplay: bool = True) -> str:
    if not query or not query.strip():
        return "Çalınacak içerik belirtilmedi."

    normalized_provider = (provider or "auto").strip().lower()
    if normalized_provider in {"yt", "youtube music"}:
        normalized_provider = "youtube"
    elif normalized_provider in {"apple music", "music", "apple_music"}:
        normalized_provider = "apple_music"

    if normalized_provider == "spotify":
        return _play_spotify(query, autoplay=autoplay)
    if normalized_provider == "apple_music":
        return _play_music_app(query, autoplay=autoplay)
    if normalized_provider == "youtube":
        return _play_youtube(query)

    # auto: masaüstü müzik uygulamalarını dener, sonra YouTube'a düşer
    if _app_exists(SPOTIFY_APP):
        result = _play_spotify(query, autoplay=autoplay)
        if "yüklü görünmüyor" not in result and "açılamadı" not in result:
            return result
    result = _play_music_app(query, autoplay=autoplay)
    if "bulunamadı" not in result:
        return result
    return _play_youtube(query)
