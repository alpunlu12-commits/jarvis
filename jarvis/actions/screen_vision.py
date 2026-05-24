# Alp Ünlü tarafından yapılmıştır — @alppunlu
from __future__ import annotations

import io
import json
import mimetypes
import os
import subprocess
import tempfile
import time
from pathlib import Path

from google import genai
from google.genai import errors, types
from PIL import Image, ImageStat

from app_config import get_app_config_value


BASE_DIR = Path(__file__).resolve().parent.parent
SWIFT_CACHE_DIR = BASE_DIR / ".swift-cache"
HELPERS_DIR = BASE_DIR / "helpers"
HELPER_SOURCE = HELPERS_DIR / "jarvis_screen_helper.swift"
HELPER_PLIST = HELPERS_DIR / "jarvis_screen_helper.plist"
HELPER_APP = HELPERS_DIR / "JARVIS Screen Helper.app"
HELPER_CONTENTS_DIR = HELPER_APP / "Contents"
HELPER_MACOS_DIR = HELPER_CONTENTS_DIR / "MacOS"
HELPER_RESOURCES_DIR = HELPER_CONTENTS_DIR / "Resources"
HELPER_INFO_PLIST = HELPER_CONTENTS_DIR / "Info.plist"
HELPER_BIN = HELPER_MACOS_DIR / "jarvis-screen-helper"

VISION_MODELS = (
    "models/gemini-2.0-flash",
    "models/gemini-2.5-flash-lite",
    "models/gemini-2.5-flash",
)
VISION_MAX_DIMENSION = 1800
VISION_MAX_INLINE_BYTES = 5_500_000


def _screen_permission_message() -> str:
    return (
        "Ekran analizi icin macOS ekran kaydi izni gerekiyor. "
        "Sistem Ayarlari > Gizlilik ve Guvenlik > Ekran Kaydi bolumune git ve "
        "JARVIS'i calistiran uygulamaya izin ver. Genelde Visual Studio Code, Python "
        "veya Terminal gorunur. Izin verdikten sonra uygulamayi kapatip yeniden dene."
    )


def _ensure_helper_binary() -> tuple[bool, str]:
    SWIFT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    HELPER_MACOS_DIR.mkdir(parents=True, exist_ok=True)
    HELPER_RESOURCES_DIR.mkdir(parents=True, exist_ok=True)

    if not HELPER_SOURCE.exists():
        return False, "Screen helper kaynak dosyasi bulunamadi."
    if not HELPER_PLIST.exists():
        return False, "Screen helper plist dosyasi bulunamadi."

    source_mtime = max(HELPER_SOURCE.stat().st_mtime, HELPER_PLIST.stat().st_mtime)
    if (
        HELPER_BIN.exists()
        and HELPER_INFO_PLIST.exists()
        and HELPER_BIN.stat().st_mtime >= source_mtime
        and HELPER_INFO_PLIST.stat().st_mtime >= source_mtime
    ):
        return True, ""

    try:
        HELPER_INFO_PLIST.write_text(HELPER_PLIST.read_text(encoding="utf-8"), encoding="utf-8")
        env = os.environ.copy()
        env["CLANG_MODULE_CACHE_PATH"] = str(SWIFT_CACHE_DIR)
        env["SWIFT_MODULE_CACHE_PATH"] = str(SWIFT_CACHE_DIR)
        result = subprocess.run(
            [
                "swiftc",
                str(HELPER_SOURCE),
                "-o",
                str(HELPER_BIN),
            ],
            capture_output=True,
            text=True,
            timeout=40,
            env=env,
        )
    except FileNotFoundError:
        return False, "swiftc bulunamadi."
    except subprocess.TimeoutExpired:
        return False, "Screen helper derlenirken zaman asimina ugradi."
    except Exception as exc:
        return False, f"Screen helper derlenemedi: {exc}"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return False, detail or "Screen helper derlenemedi."

    try:
        HELPER_BIN.chmod(0o755)
    except Exception:
        pass
    return True, ""


def _run_helper(mode: str, timeout: int = 20) -> tuple[bool, str]:
    ok, detail = _ensure_helper_binary()
    if not ok:
        return False, detail

    output_path = None
    raw = ""
    try:
        handle = tempfile.NamedTemporaryFile(prefix="jarvis-screen-helper-", suffix=".json", delete=False)
        output_path = Path(handle.name)
        handle.close()
        result = subprocess.run(
            ["open", "-W", "-n", str(HELPER_APP), "--args", mode, str(output_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, "Screen helper istegi zaman asimina ugradi."
    except Exception as exc:
        return False, f"Screen helper calistirilamadi: {exc}"

    if output_path and output_path.exists():
        try:
            raw = output_path.read_text(encoding="utf-8").strip()
        except Exception:
            raw = ""

    final_raw = raw or (result.stdout or "").strip()
    if result.returncode != 0:
        final_raw = raw

    if not final_raw:
        try:
            result = subprocess.run(
                [str(HELPER_BIN), mode, str(output_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if output_path and output_path.exists():
                try:
                    final_raw = output_path.read_text(encoding="utf-8").strip()
                except Exception:
                    final_raw = ""
            if not final_raw and result.returncode == 0:
                final_raw = (result.stdout or "").strip()
            if result.returncode != 0 and not final_raw:
                detail = (result.stderr or result.stdout or "").strip()
                return False, detail or "Screen helper calismadi."
        except subprocess.TimeoutExpired:
            return False, "Screen helper istegi zaman asimina ugradi."
        except Exception as exc:
            return False, f"Screen helper calistirilamadi: {exc}"
    try:
        if output_path and output_path.exists():
            output_path.unlink()
    except Exception:
        pass

    return True, final_raw


def _parse_capture_payload(raw: str) -> tuple[bool, str, dict | None]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return False, "Gecersiz ekran helper yaniti alindi.", None

    if not isinstance(payload, dict):
        return False, "Ekran helper verisi beklenen formatta degil.", None

    if not payload.get("ok", False):
        detail = str(payload.get("detail") or payload.get("error") or "Ekran goruntusu alinamadi.")
        low = detail.lower()
        if "permission" in low or "not permitted" in low or "screen recording" in low:
            return False, _screen_permission_message(), None
        if str(payload.get("error") or "").lower() == "permission_denied":
            return False, _screen_permission_message(), None
        return False, detail, None

    image_path = str(payload.get("image_path", "")).strip()
    if not image_path:
        return False, "Ekran goruntusu dosya yolu alinamadi.", None

    meta = {
        "image_path": image_path,
        "owner_name": str(payload.get("owner_name", "")).strip(),
        "window_title": str(payload.get("window_title", "")).strip(),
        "bounds": payload.get("bounds") or {},
        "detail": str(payload.get("detail", "")).strip(),
    }
    return True, "", meta


def _image_looks_blank(image_path: Path) -> bool:
    try:
        with Image.open(image_path) as img:
            sample = img.convert("RGB")
            stat = ImageStat.Stat(sample)
            means = stat.mean
            extrema = stat.extrema
            max_seen = max(channel[1] for channel in extrema)
            mean_total = sum(means) / max(1, len(means))
            return max_seen <= 8 or mean_total <= 3
    except Exception:
        return False


def _build_image_part(image_path: Path) -> types.Part:
    mime_type, _ = mimetypes.guess_type(str(image_path))
    if not mime_type:
        mime_type = "image/png"

    try:
        with Image.open(image_path) as img:
            work = img.copy()
        if work.mode not in {"RGB", "L"}:
            work = work.convert("RGB")

        if max(work.size) > VISION_MAX_DIMENSION:
            work.thumbnail((VISION_MAX_DIMENSION, VISION_MAX_DIMENSION), Image.Resampling.LANCZOS)

        png_buffer = io.BytesIO()
        work.save(png_buffer, format="PNG", optimize=True)
        png_bytes = png_buffer.getvalue()
        if len(png_bytes) <= VISION_MAX_INLINE_BYTES:
            return types.Part.from_bytes(data=png_bytes, mime_type="image/png")

        jpg_buffer = io.BytesIO()
        rgb = work.convert("RGB") if work.mode != "RGB" else work
        rgb.save(jpg_buffer, format="JPEG", quality=88, optimize=True)
        return types.Part.from_bytes(data=jpg_buffer.getvalue(), mime_type="image/jpeg")
    except Exception:
        return types.Part.from_bytes(
            data=image_path.read_bytes(),
            mime_type=mime_type,
        )


def _vision_prompt(query: str, owner_name: str, window_title: str) -> str:
    label = window_title or owner_name or "aktif pencere"
    user_query = (query or "Ekranda ne var?").strip()
    return (
        "Sen macOS uzerinde JARVIS icin ekran analizi yapan bir goruntu yorumlayicisisin.\n"
        "Asagidaki ekran goruntusu aktif pencereye ait.\n"
        f"Pencere baglami: {label}\n\n"
        "Gorevlerin:\n"
        "1. Pencerenin genel amacini 1-2 cumlede acikla.\n"
        "2. Gorunen onemli metinleri, hata mesajlarini, butonlari, basliklari ve durum etiketlerini oku.\n"
        "3. Kullanici sorusunu bu goruntuye gore dogrudan cevapla.\n"
        "4. Eger bir hata, uyari veya dikkat edilmesi gereken bir sey varsa bunu ayri ve net belirt.\n"
        "5. Uydurma yapma. Emin olmadigin kisimlarda bunu soyle.\n\n"
        f"Kullanici sorusu: {user_query}\n\n"
        "Yaniti Turkce ver. Gereksiz uzun olma, ama okunabilir detay ver."
    )


def _extract_response_text(response) -> str:
    text = str(getattr(response, "text", "") or "").strip()
    if text:
        return text

    candidates = getattr(response, "candidates", None) or []
    chunks: list[str] = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            part_text = str(getattr(part, "text", "") or "").strip()
            if part_text:
                chunks.append(part_text)
    return "\n".join(chunk for chunk in chunks if chunk).strip()


def _is_transient_vision_error(exc: Exception) -> bool:
    if isinstance(exc, (errors.ServerError, TimeoutError)):
        return True

    message = str(exc or "").lower()
    transient_markers = (
        "503",
        "429",
        "deadline",
        "timed out",
        "timeout",
        "unavailable",
        "temporarily unavailable",
        "service unavailable",
        "internal error",
        "busy",
        "overloaded",
        "resource exhausted",
        "try again later",
        "backend error",
        "connection reset",
    )
    return any(marker in message for marker in transient_markers)


def _is_quota_vision_error(exc: Exception) -> bool:
    message = str(exc or "").lower()
    quota_markers = (
        "quota",
        "rate limit",
        "resource exhausted",
        "too many requests",
        "quota exceeded",
        "limit exceeded",
        "billing",
    )
    return any(marker in message for marker in quota_markers)


def _friendly_vision_error(exc: Exception) -> str:
    if _is_quota_vision_error(exc):
        return "Gemini vision istegi kota veya hiz limitine takildi. Biraz bekleyip tekrar dene ya da API planini kontrol et."
    if _is_transient_vision_error(exc):
        return "Gemini vision servisi su anda yogun veya gecici olarak ulasilamiyor. Biraz sonra tekrar dene."
    return f"Gemini vision istegi basarisiz oldu: {exc}"


def _analyze_with_gemini(query: str, image_path: Path, owner_name: str, window_title: str) -> str:
    api_key = str(get_app_config_value("gemini_api_key", "") or "").strip()
    if not api_key:
        return "Gemini API anahtari eksik oldugu icin ekran analizi yapilamadi."

    prompt = _vision_prompt(query, owner_name, window_title)
    client = genai.Client(api_key=api_key)
    image_part = _build_image_part(image_path)
    retry_delays = (0.9, 1.8, 3.0)
    last_error: Exception | None = None

    for model_name in VISION_MODELS:
        for attempt, delay in enumerate(retry_delays, start=1):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Part.from_text(text=prompt),
                        image_part,
                    ],
                    config=types.GenerateContentConfig(
                        temperature=0.2,
                    ),
                )
                merged = _extract_response_text(response)
                if merged:
                    return merged
                raise RuntimeError("Gemini gecerli bir ekran analizi metni dondurmedi.")
            except Exception as exc:
                last_error = exc
                if attempt < len(retry_delays) and _is_transient_vision_error(exc):
                    time.sleep(delay)
                    continue
                if _is_transient_vision_error(exc):
                    break
                raise RuntimeError(_friendly_vision_error(exc)) from exc

    assert last_error is not None
    raise RuntimeError(_friendly_vision_error(last_error))


def analyze_screen(query: str, target: str = "active_window") -> str:
    target = (target or "active_window").strip().lower()
    if target != "active_window":
        return "Screen Vision v1 yalnizca aktif pencere analizini destekliyor."

    ok, raw = _run_helper("capture_active_window", timeout=20)
    if not ok:
        low = raw.lower()
        if "permission" in low or "screen recording" in low:
            return _screen_permission_message()
        return f"Ekran goruntusu alinamadi: {raw}"

    parsed_ok, detail, payload = _parse_capture_payload(raw)
    if not parsed_ok:
        return detail

    assert payload is not None
    image_path = Path(payload["image_path"])
    owner_name = str(payload.get("owner_name", "") or "").strip()
    window_title = str(payload.get("window_title", "") or "").strip()

    try:
        if not image_path.exists():
            return "Ekran goruntusu dosyasi bulunamadi. Tekrar dene."
        if image_path.stat().st_size <= 0:
            return (
                "Ekran goruntusu bos geldi. Bu genelde ekran kaydi izni olmadiginda "
                "veya korumali bir pencere acikken olur. " + _screen_permission_message()
            )
        if _image_looks_blank(image_path):
            return (
                "Ekran goruntusu siyah veya bos gorunuyor. Bu, ekran kaydi izni eksik oldugunda "
                "ya da korumali bir uygulama acikken olabilir. " + _screen_permission_message()
            )
        try:
            analysis = _analyze_with_gemini(query, image_path, owner_name, window_title)
        except Exception as exc:
            prefix = f"{owner_name} / {window_title}".strip(" /")
            if prefix:
                return (
                    f"Ekran goruntusu alindi ({prefix}) ama analiz tamamlanamadi: {exc}"
                )
            return f"Ekran goruntusu alindi ama analiz tamamlanamadi: {exc}"

        if owner_name or window_title:
            title = " / ".join(part for part in (owner_name, window_title) if part).strip()
            if title:
                return f"[Aktif pencere: {title}]\n{analysis}"
        return analysis
    finally:
        try:
            if image_path.exists():
                image_path.unlink()
        except Exception:
            pass
