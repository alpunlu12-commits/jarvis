# JARVIS — Lokal AI Asistanı (v4)

> Just A Rather Very Intelligent System — Tkinter HUD, Apple-design koyu tema, **tam lokal, ücretsiz, offline çalışır**.

## ✨ v4 Yenilikler

- **Yuvarlak Stark HUD** — dönen dış/iç halkalar (0.5° / -0.7° per tick), 60 tick, pulsing core — tam Stark dairesi
- **Tam ekran** — açılışta maximize, **F11** ile fullscreen aç/kapa, pencere resize'da otomatik relayout (canvas + paneller)
- **Telefon QR kontrol (lokal)** — aynı Wi-Fi'da telefon → QR tarat → `http://<pc-ip>:8765?token=...` → telefondan komut yaz → PC'de çalışır (FastAPI + WebSocket, **ücretsiz, cloud yok**)
- **Harf toleransı** — `c↔j` `s↔ş↔ç` `z→c` normalize → `sak/şak/çak` aynı, `cak/jak/zak` aynı, `ac/as/aç` aynı — yanlış telaffuzda da anlar
- **Dinleme fix** — mikrofon **F4 / LIVE** ile opt-in (pyaudio ACCESS_VIOLATION güvenli mod), yoksa yazarak stabil

## Özellikler

- Koyu HUD — teal vurgulu, yuvarlak köşeli paneller
- Durum: LISTENING / THINKING / SPEAKING / ERROR / PAUSED
- Sistem paneli: CPU, RAM, Disk, Pil, Saat (+ 20-bar CPU hist)
- Hava durumu paneli
- Komut girişi: metin + sesli (wake word "jarvis" + çift alkış)
- TTS: edge-tts (Emel/Ahmet tr-TR) → pyttsx3 → SAPI
- Hafıza: JSON kalıcı bellek + phone_book
- Araçlar: open_app, sys_info, weather, browser, shell (whitelist 26 komut), media, memory, health, tts voice

## Kurulum

```bat
:: Windows — çift tık
jarvis\setup.bat

:: veya manuel
pip install -r requirements.txt
python -X utf8 -u main.py
```

## PowerShell ile Çalıştırma

```powershell
Set-Location "C:\Users\kygsz\testproje4\jarvis"
$env:PYTHONUTF8 = "1"
python -X utf8 -u main.py

# log ile
python -X utf8 -u main.py 2>&1 | Tee-Object .\run.log
Get-Content .\run.log -Tail 40
```

Çift tık: `JARVIS.bat` (chcp 65001 + PYTHONUTF8=1), debug: `JARVIS_DEBUG.bat`

## Kullanım

| Komut | Action |
|-------|--------|
| `Merhaba` | Selamlaşma |
| `Spotify'ı aç / as / aç` | Uygulama açma (tolerant) |
| `Pil durumu nedir?` | Sistem bilgisi |
| `İstanbul'da hava nasıl?` | Hava durumu |
| `Google'da Python öğren` | Tarayıcı arama |
| `YouTube'dan The Weeknd aç` | Medya |
| `Bunu hafızana kaydet` | Hafıza |
| `Terminalde dir yazdır` | Shell (whitelist) |
| `Sesini değiştir / erkek yap` | TTS Emel↔Ahmet |

### Kısayollar

| Tuş | İşlev |
|-----|-------|
| `F4` / LIVE | Mikrofon aç/kapa (opt-in) |
| `F5` / PAUSE | Durdur/devam |
| `F11` | Tam ekran aç/kapa |
| `ESC` | Çıkış |
| `Enter` | Komut gönder |

### Telefon QR Kullanımı

1. PC'de `python main.py` → sol panel **PHONE LINK** → **TELEFON** butonu → QR popup
2. Telefon aynı Wi-Fi'da → QR tarat → PWA açılır
3. Telefona yaz: `notepad ac`, `hava nasıl`, `youtube aç` → PC'de çalışır, sonuç telefona döner
4. Token her başlatmada yenilenir (`secrets.token_urlsafe`), sadece yerel ağ

## Harf Toleransı Örnekleri

```
sak = şak = çak
cak = jak = zak
notepad ac = notepad as = notepad aç
```

Normalize: `ı→i ğ→g ü→u ö→o`, sonra `c/j/z→c`, `s/ş/ç→s`

## Yapılandırma — config/api_keys.json

```json
{
  "gemini_api_key": "",
  "voice": "tr-TR-EmelNeural",
  "language": "tr",
  "offline_mode": true
}
```

## Proje Yapısı

```
jarvis/
├── main.py              # Orchestrator + PhoneServer + voice opt-in + tam ekran
├── ui.py                # Tkinter HUD — dairesel HUD + relayout + fullscreen
├── requirements.txt     # psutil, Pillow, mss, SpeechRecognition, edge-tts, fastapi, uvicorn, qrcode
├── JARVIS.bat / JARVIS_DEBUG.bat
├── config/app_config.py
├── core/engine.py       # normalize + tolerant parse (c/j/z, s/ş/ç)
├── memory/memory_manager.py
├── voice/listener.py
├── wakeup_listener.py
├── server/phone_server.py  # FastAPI + WebSocket + QR
│   └── static/index.html   # PWA
└── actions/ (open_app, sys_info, weather, browser, shell, media, health, tts, screen_vision)
```

## Gereksinimler

- Python 3.10+ (3.11 testli), Windows 10/11, mikrofon opsiyonel, internet opsiyonel (hava + STT)

## Lisans

MIT — Orijinal referans Alp Ünlü (@alppunlu), v4 lokal/ücretsiz genişletme Sisyphus.
