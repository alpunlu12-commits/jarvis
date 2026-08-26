"""JARVIS Phone Server — Lokal telefon kontrol API'si.

FastAPI + WebSocket tabanlı sunucu. Telefondan komut göndermek için
QR kodu taratılarak bağlanılır. Tüm iletişim yerel ağ üzerindendir.

Kullanım:
    from jarvis.server import PhoneServer

    def handle(text: str) -> str:
        return f"Komut alındı: {text}"

    ps = PhoneServer(command_handler=handle)
    ps.start()
    print(ps.get_url())      # http://192.168.1.x:8765?token=...
    print(ps.get_qr_data())  # base64 PNG QR kodu

Author: JARVIS Project
License: MIT (local use only)
"""

from __future__ import annotations

import asyncio
import io
import logging
import secrets
import socket
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger("jarvis.server")

# ── Sabitler ──────────────────────────────────────────────────────────────
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_DEFAULT_PORT = 8765
_STARTUP_TIMEOUT = 5.0  # saniye — uvicorn thread'inin başlaması için bekleme
_HEALTH_CHECK_TIMEOUT = 2.0


# ── Yardımcı: Yerel IP adresi ────────────────────────────────────────────
def _get_local_ip() -> str:
    """Yerel ağ IP adresini döndür. Çoklu yöntem dener."""
    # Yöntem 1: socket trick (en güvenilir, dış bağlantiya gerek yok)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            # Paket gitmez bile — sadece arayüz IP'sini öğrenir
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
            if ip and ip != "127.0.0.1":
                return str(ip)
    except Exception:
        pass

    # Yöntem 2: psutil
    try:
        import psutil

        for _name, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                    return str(addr.address)
    except Exception:
        pass

    # Yöntem 3: socket.gethostbyname
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and not ip.startswith("127."):
            return str(ip)
    except Exception:
        pass

    return "127.0.0.1"


# ── QR Kod Üreteci ───────────────────────────────────────────────────────
def _generate_qr_png(data: str) -> Optional[bytes]:
    """QR kodu PNG olarak üretir. qrcode/pillow yoksa None döner."""
    try:
        import qrcode
        from PIL import Image

        qr = qrcode.QRCode(
            version=None,  # otomatik boyut
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="#00d4c0", back_color="#0a0a10")
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except ImportError:
        logger.warning("qrcode/pillow bulunamadi — QR PNG uretilemez.")
        return None
    except Exception as e:
        logger.warning("QR uretim hatasi: %s", e)
        return None


# ── Pydantic Modeller ────────────────────────────────────────────────────
class CommandRequest(BaseModel):
    """POST /api/command istek modeli."""

    token: str
    text: str


class CommandResponse(BaseModel):
    """POST /api/command yanıt modeli."""

    ok: bool
    result: str = ""
    error: str = ""


class StatusResponse(BaseModel):
    """GET /api/status yanıt modeli."""

    running: bool
    port: int
    url: str
    token_masked: str  # son 4 karakteri görünür
    has_handler: bool


# ═══════════════════════════════════════════════════════════════════════════
#  PhoneServer — Ana Sınıf
# ═══════════════════════════════════════════════════════════════════════════
class PhoneServer:
    """Lokal telefon kontrol sunucusu.

    FastAPI uygulamasını daemon thread'de çalıştırır.
    QR kodu ile telefondan taranarak bağlanılır.
    Tüm iletişim yerel ağ üzerindedir — dış servis gerektirmez.
    """

    def __init__(
        self,
        command_handler: Optional[Callable[[str], str]] = None,
        port: int = _DEFAULT_PORT,
    ) -> None:
        self._port = port
        self._token: str = secrets.token_urlsafe(16)
        self._local_ip: str = _get_local_ip()
        self._running = False
        self._server_thread: Optional[threading.Thread] = None
        self._command_handler: Optional[Callable[[str], str]] = command_handler
        self._ws_clients: list[WebSocket] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._app: Optional[FastAPI] = None
        self._actual_port: int = port

    # ── Public API ────────────────────────────────────────────────────────

    def set_command_handler(self, handler: Callable[[str], str]) -> None:
        """Komut işleyici callback'ini ayarla.

        main.py'den _on_text_command fonksiyonu buraya enjekte edilir.
        """
        self._command_handler = handler

    def start(self, port: Optional[int] = None) -> None:
        """Sunucuyu arka planda başlatır (daemon thread).

        Otomatik olarak port yoksa 8765'ten başlayarak müsait port arar.
        """
        if self._running:
            logger.warning("PhoneServer zaten çalışıyor.")
            return

        if port is not None:
            self._port = port

        self._token = secrets.token_urlsafe(16)
        self._local_ip = _get_local_ip()
        self._app = self._build_app()

        # Otomatik port bul
        actual_port = self._find_available_port(self._port)
        self._actual_port = actual_port

        self._running = True
        self._server_thread = threading.Thread(
            target=self._run_server,
            args=(actual_port,),
            daemon=True,
            name="PhoneServer",
        )
        self._server_thread.start()

        # Başlamasını bekle
        import time

        deadline = time.monotonic() + _STARTUP_TIMEOUT
        while time.monotonic() < deadline:
            if self._loop is not None:
                break
            time.sleep(0.1)

        if self._loop is None:
            logger.error("PhoneServer baslatilamadi (timeout).")
            self._running = False
            return

        logger.info(
            "PhoneServer baslatildi: %s:%d?token=%s",
            self._local_ip,
            actual_port,
            self._token[:8] + "...",
        )

    def stop(self) -> None:
        """Sunucuyu durdurur."""
        if not self._running:
            return

        self._running = False

        if self._loop and self._loop.is_running():
            # Tüm WebSocket bağlantılarını kapat
            for ws in list(self._ws_clients):
                try:
                    self._loop.call_soon_threadsafe(
                        asyncio.ensure_future, ws.close()
                    )
                except Exception:
                    pass
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=3.0)

        self._server_thread = None
        self._loop = None
        logger.info("PhoneServer durduruldu.")

    def get_url(self) -> str:
        """HTTP erişim URL'ini döndür."""
        return f"http://{self._local_ip}:{self._actual_port}?token={self._token}"

    def get_ws_url(self) -> str:
        """WebSocket URL'ini döndür."""
        return f"ws://{self._local_ip}:{self._actual_port}/ws?token={self._token}"

    def get_qr_data(self) -> Optional[str]:
        """QR kodunu base64 PNG olarak döndür. qrcode yoksa text URL döner."""
        ws_url = self.get_ws_url()
        png = _generate_qr_png(ws_url)
        if png is not None:
            import base64

            return base64.b64encode(png).decode("ascii")
        return None

    def get_qr_image_bytes(self) -> Optional[bytes]:
        """QR kodunu raw PNG bytes olarak döndür."""
        return _generate_qr_png(self.get_ws_url())

    @property
    def is_running(self) -> bool:
        """Sunucu çalışıyor mu?"""
        return self._running

    @property
    def port(self) -> int:
        """Aktif port."""
        return self._actual_port

    @property
    def token(self) -> str:
        """Erişim token'ı."""
        return self._token

    # ── Dahili ─────────────────────────────────────────────────────────────

    def _build_app(self) -> FastAPI:
        """FastAPI uygulamasını oluşturur."""
        app = FastAPI(
            title="JARVIS Phone Control",
            description="Lokal telefon kontrol arayuzu",
            version="1.0.0",
            docs_url=None,  # production'da docs kapalı
            redoc_url=None,
        )

        # CORS — yerel ağ için serbest
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Statik dosyalar
        if _STATIC_DIR.exists():
            app.mount(
                "/static",
                StaticFiles(directory=str(_STATIC_DIR)),
                name="static",
            )

        # ── Route'lar ─────────────────────────────────────────────────

        @app.get("/", response_class=HTMLResponse)
        async def index() -> HTMLResponse:
            """Ana sayfa — PWA arayüzü."""
            index_file = _STATIC_DIR / "index.html"
            if index_file.exists():
                html = index_file.read_text(encoding="utf-8")
                return HTMLResponse(content=html)
            return HTMLResponse(
                content="<h1>JARVIS Phone Control</h1><p>Static dosya bulunamadı.</p>"
            )

        @app.get("/api/status")
        async def status() -> StatusResponse:
            """Sunucu durumu."""
            return StatusResponse(
                running=self._running,
                port=self._actual_port,
                url=self.get_url(),
                token_masked="..." + self._token[-4:],
                has_handler=self._command_handler is not None,
            )

        @app.post("/api/command", response_model=CommandResponse)
        async def command(req: CommandRequest) -> CommandResponse:
            """HTTP komut endpoint'i — WebSocket fallback."""
            if req.token != self._token:
                return CommandResponse(ok=False, error="Gecersiz token.")

            if not self._command_handler:
                return CommandResponse(ok=False, error="Komut isleyici tanimli degil.")

            try:
                # Blocking handler'ı thread pool'da çalıştır
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, self._command_handler, req.text
                )
                return CommandResponse(ok=True, result=str(result))
            except Exception as e:
                return CommandResponse(ok=False, error=str(e))

        @app.get("/api/qr", response_model=None)
        async def qr():  # type: ignore[no-untyped-def]
            """QR kodu PNG olarak döndür."""
            img_bytes = self.get_qr_image_bytes()
            if img_bytes:
                return StreamingResponse(
                    io.BytesIO(img_bytes),
                    media_type="image/png",
                    headers={"Cache-Control": "no-cache"},
                )
            # Fallback: JSON ile text URL
            return JSONResponse(
                {
                    "url": self.get_ws_url(),
                    "message": "qrcode kutuphanesi bulunamadi — URL'i manuel kopyalayin.",
                }
            )

        @app.websocket("/ws")
        async def websocket_endpoint(ws: WebSocket) -> None:
            """WebSocket komut kanalı."""
            # Token doğrulama
            token = ws.query_params.get("token", "")
            if token != self._token:
                await ws.close(code=4001, reason="Gecersiz token.")
                return

            await ws.accept()
            self._ws_clients.append(ws)
            logger.info("WebSocket baglandi (toplam: %d)", len(self._ws_clients))

            try:
                while self._running:
                    data = await ws.receive_text()
                    # Komutu işle
                    if not self._command_handler:
                        await ws.send_json(
                            {"ok": False, "error": "Komut isleyici tanimli degil."}
                        )
                        continue

                    try:
                        loop = asyncio.get_event_loop()
                        result = await loop.run_in_executor(
                            None, self._command_handler, data
                        )
                        await ws.send_json({"ok": True, "result": str(result)})
                    except Exception as e:
                        await ws.send_json({"ok": False, "error": str(e)})
            except WebSocketDisconnect:
                pass
            except Exception as e:
                logger.warning("WebSocket hatasi: %s", e)
            finally:
                if ws in self._ws_clients:
                    self._ws_clients.remove(ws)
                logger.info(
                    "WebSocket koptu (kalan: %d)", len(self._ws_clients)
                )

        return app

    def _run_server(self, port: int) -> None:
        """uvicorn'u daemon thread'de çalıştırır."""
        import uvicorn

        config = uvicorn.Config(
            app=self._app,  # type: ignore[arg-type]
            host="0.0.0.0",
            port=port,
            log_level="warning",
            access_log=False,
            use_colors=False,
        )
        server = uvicorn.Server(config)

        # Event loop'u bu thread'de oluştur
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(server.serve())
        except Exception as e:
            logger.error("uvicorn hatasi: %s", e)
        finally:
            self._running = False

    @staticmethod
    def _find_available_port(start: int) -> int:
        """Verilen port'tan başlayarak müsait bir port bulur."""
        for port in range(start, start + 100):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind(("0.0.0.0", port))
                    return port
            except OSError:
                continue
        return start  # fallback — hata verir ama en azından çalışır


# ── Modül seviyesi erişim (test/debug) ───────────────────────────────────
_default_server: Optional[PhoneServer] = None


def get_server() -> Optional[PhoneServer]:
    """Varsayılan PhoneServer örneğini döndür."""
    return _default_server


def create_server(
    command_handler: Optional[Callable[[str], str]] = None,
    port: int = _DEFAULT_PORT,
) -> PhoneServer:
    """Yeni bir PhoneServer oluşturur ve modül seviyesinde saklar."""
    global _default_server  # noqa: PLW0603
    _default_server = PhoneServer(command_handler=command_handler, port=port)
    return _default_server
