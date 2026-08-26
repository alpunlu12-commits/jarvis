"""
Ekran goruntusu analizi — mss + ctypes + Pillow.
Gemini API opsiyonel: yoksa lokal analiz (pencere basligi, cozunurluk).
"""

from __future__ import annotations

import ctypes
import io
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ImageStat
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

try:
    import mss, mss.tools
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

try:
    from google import genai
    from google.genai import errors as genai_errors, types as genai_types
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

try:
    from ..config.app_config import get_app_config_value
except ImportError:
    def get_app_config_value(key: str, default: object = None) -> object:
        return os.environ.get(key, default if default is not None else "")

VISION_MODELS = ("models/gemini-2.0-flash", "models/gemini-2.5-flash-lite", "models/gemini-2.5-flash")
VISION_MAX_DIM = 1800
VISION_MAX_BYTES = 5_500_000
_MAX_SCREENSHOT = 20 * 1024 * 1024


def _get_active_window_title() -> str:
    try:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value.strip()
    except Exception:
        return ""


def _get_resolution() -> tuple[int, int]:
    try:
        u = ctypes.windll.user32  # type: ignore[attr-defined]
        return u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    except Exception:
        return 0, 0


def _capture() -> tuple[bool, str, str]:
    """(ok, file_path, window_title) dondurur."""
    if not HAS_MSS or not HAS_PILLOW:
        return False, "mss/Pillow gerekli: pip install mss Pillow", ""
    title = _get_active_window_title()
    try:
        with mss.mss() as sct:
            mon = sct.monitors[1]
            shot = sct.grab(mon)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    except Exception as exc:
        return False, f"Screenshot alinamadi: {exc}", ""
    try:
        handle = tempfile.NamedTemporaryFile(prefix="jarvis-", suffix=".png", delete=False)
        p = Path(handle.name)
        handle.close()
        img.save(str(p), format="PNG")
        if p.stat().st_size > _MAX_SCREENSHOT:
            p.unlink(missing_ok=True)
            return False, "Screenshot cok buyuk.", ""
    except Exception as exc:
        return False, f"Kaydetme hatasi: {exc}", ""
    return True, str(p), title


def _image_blank(p: Path) -> bool:
    if not HAS_PILLOW:
        return False
    try:
        with Image.open(p) as img:
            s = ImageStat.Stat(img.convert("RGB"))
            mx = max(ch[1] for ch in s.extrema)
            avg = sum(s.mean) / max(1, len(s.mean))
            return mx <= 8 or avg <= 3
    except Exception:
        return False


def _local_analysis(title: str, p: Path) -> str:
    w, h = _get_resolution()
    sz = p.stat().st_size / 1024 if p.exists() else 0
    t = title or "Bilinmeyen pencere"
    lines = [
        "Ekran goruntusu yakalandi — lokal analiz:",
        f"  Cozunurluk : {w}x{h}",
        f"  Aktif pencere: {t}",
        f"  Dosya boyutu : {sz:.0f} KB",
    ]
    if HAS_PILLOW:
        try:
            with Image.open(p) as img:
                stat = ImageStat.Stat(img.convert("RGB"))
                br = sum(stat.mean[:3]) / 3.0
                lines.append(f"  Parlaklik: {br:.0f}/255")
                if br < 30:
                    lines.append("  Not: Ekran karanlik.")
                elif br > 230:
                    lines.append("  Not: Ekran cok parlak.")
        except Exception:
            pass
    lines.append("\nGemini API olmadan gorsel analiz yapilmaz.")
    lines.append("Gercek analiz icin GEMINI_API_KEY ayarla.")
    return "\n".join(lines)


# ── Gemini (opsiyonel) ────────────────────────────────────────────────

def _build_prompt(q: str, title: str) -> str:
    return (
        "Sen JARVIS icin ekran analizcisisin. Pencere: " + (title or "aktif") + "\n"
        "1. Pencere amacini acikla. 2. Metin/hata oku. 3. Soruyu cevapla.\n"
        "Turkce, kisa, net. Uydurma yapma.\nSoru: " + (q or "Ekranda ne var?")
    )


def _extract_text(resp: object) -> str:
    t = str(getattr(resp, "text", "") or "").strip()
    if t:
        return t
    parts: list[str] = []
    for c in getattr(resp, "candidates", None) or []:
        for p in getattr(getattr(c, "content", None), "parts", None) or []:
            pt = str(getattr(p, "text", "") or "").strip()
            if pt:
                parts.append(pt)
    return "\n".join(parts)


def _build_part(p: Path) -> "genai_types.Part":
    import mimetypes
    mt, _ = mimetypes.guess_type(str(p))
    mt = mt or "image/png"
    try:
        with Image.open(p) as img:
            work = img.copy()
        if work.mode not in {"RGB", "L"}:
            work = work.convert("RGB")
        if max(work.size) > VISION_MAX_DIM:
            work.thumbnail((VISION_MAX_DIM, VISION_MAX_DIM), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        work.save(buf, format="PNG", optimize=True)
        if len(buf.getvalue()) <= VISION_MAX_BYTES:
            return genai_types.Part.from_bytes(data=buf.getvalue(), mime_type="image/png")
        buf2 = io.BytesIO()
        work.convert("RGB").save(buf2, format="JPEG", quality=88, optimize=True)
        return genai_types.Part.from_bytes(data=buf2.getvalue(), mime_type="image/jpeg")
    except Exception:
        return genai_types.Part.from_bytes(data=p.read_bytes(), mime_type=mt)


def _transient(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    if HAS_GEMINI and isinstance(exc, genai_errors.ServerError):
        return True
    m = str(exc or "").lower()
    return any(x in m for x in ("503", "429", "timeout", "unavailable", "busy"))


def _gemini_analyze(q: str, p: Path, title: str) -> str:
    key = str(get_app_config_value("gemini_api_key", "") or "").strip()
    if not key:
        return ""
    client = genai.Client(api_key=key)
    image_part = _build_part(p)
    prompt = _build_prompt(q, title)
    for model in VISION_MODELS:
        for attempt, delay in enumerate((0.9, 1.8, 3.0), 1):
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=[genai_types.Part.from_text(text=prompt), image_part],
                    config=genai_types.GenerateContentConfig(temperature=0.2),
                )
                txt = _extract_text(resp)
                if txt:
                    return txt
            except Exception as exc:
                if attempt < 3 and _transient(exc):
                    time.sleep(delay)
                    continue
                if _transient(exc):
                    break
                raise RuntimeError(f"Gemini hatasi: {exc}") from exc
    return ""


# ── Ana fonksiyon ──────────────────────────────────────────────────────

def analyze_screen(query: str = "", target: str = "active_window") -> str:
    """
    Ekran goruntusu al ve analiz et.
    Gemini varsa gorsel analiz, yoksa lokal analiz.
    """
    if not HAS_MSS:
        return "mss gerekli: pip install mss Pillow"

    ok, result, title = _capture()
    if not ok:
        return f"Hata: {result}"

    p = Path(result)
    try:
        if not p.exists() or p.stat().st_size <= 0:
            return "Screenshot bos bulunamadi."
        if _image_blank(p):
            return "Screenshot siyah/bos gorunuyor."

        if HAS_GEMINI:
            try:
                a = _gemini_analyze(query, p, title)
                if a:
                    return f"[Pencere: {title}]\n{a}" if title else a
            except Exception:
                pass

        return _local_analysis(title, p)
    finally:
        p.unlink(missing_ok=True)
