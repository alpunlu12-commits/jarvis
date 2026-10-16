# JARVIS Proje Haritası (Map)

Bu belge, proje içerisindeki dosyaların, modüllerin ve asistan yeteneklerinin bir haritasıdır. Dosyalar, içerdikleri fonksiyonlar ve sistem kısıtlamaları burada detaylandırılmıştır.

## Kök Dizin Dosyaları

- **`main.py`**: Projenin ana çalıştırma dosyasıdır. Gemini ve Ollama bağlantılarını (`JarvisLive` sınıfı) asenkron olarak yönetir. Mikrofon girdilerini dinler, asistan araçlarını (tools) çağırır, Text-to-Speech (TTS) tetikler. AI tarafından oluşturulan fonksiyon (Tool Calling) isteklerinin yönetimi ve işlenmesi buradadır.
- **`ui.py`**: Tkinter tabanlı grafiksel kullanıcı arayüzünü (GUI) barındırır. Ayarlar paneli, log/konsol çıktısı, ses dalgaları, mikrofon ve sessize alma (mute) gibi kontrolleri sağlar.
- **`app_config.py`**: Uygulamanın ayarlarını (`ai_provider`, `ollama_host`, `ollama_model`, API key vb.) `config/api_keys.json` dosyasından okur ve kaydeder.
- **`setup_mac.sh` / `setup_ubuntu.sh` / `setup_windows.bat`**: İşletim sistemine özel bağımlılık kurulum scriptleridir.

## Çekirdek Modüller (`core/` ve `memory/`)

- **`core/prompt.txt`**: **Asistanın Anayasası (Sistem Prompt'u) burada yer alır.** Asistanın nasıl davranacağı, hangi dilde konuşacağı, araçları (tools) ne zaman ve hangi parametrelerle çağıracağı burada detaylıca anlatılır.
- **`memory/memory_manager.py`**: Kalıcı bellek (memory) yönetimini sağlar. `load_memory()`, `update_memory()`, ve `delete_memory()` fonksiyonları sayesinde kullanıcının anlattığı önemli bilgileri (kategori bazlı veya metin arama bazlı) `memory/memory.json` dosyasına okur/yazar.

## Aksiyon Modülleri (`actions/`)

Bu klasördeki dosyalar, asistanın çalıştırabildiği sistem yeteneklerini içerir. Önceden sadece macOS destekli olan bu modüller, Cross-Platform (Windows/Ubuntu) destekli hale getirilmiştir.

- **`actions/shell.py`**:
  - **İşlev**: Terminal komutlarını çalıştırır (`shell_run`).
  - **Kısıtlamalar ve Güvenlik**: Bu dosya, sistem için çok kritik olan *tehlikeli komutları otonom olarak reddeder*.
    - **BLOCKED listesi**: `rm -rf /`, `sudo rm -rf`, `mkfs`, `dd if=`, `:(){:|:&};:`, `shutdown`, `reboot`, `halt`, `diskutil erase`, `format` vb. engellenmiştir.
    - **Başlangıç Koruması**: Komut `rm `, `mv `, `cp `, `chmod `, `chown `, `sudo `, `del `, veya `rmdir ` ile başlıyorsa, asistan "Güvenlik: Dosya veya yetki değiştiren komutlar doğrudan çalıştırılmıyor" hatası döndürür.
- **`actions/whatsapp.py`**:
  - **İşlev**: `send_whatsapp_message` ve `save_whatsapp_contact` fonksiyonlarını içerir. Kişi adına göre veya doğrudan numarayla WhatsApp Desktop veya Web üzerinden mesaj gönderir (veya taslak açar).
- **`actions/media.py`**:
  - **İşlev**: `play_media` fonksiyonunu içerir. YouTube, Spotify veya Apple Music/Music uygulamaları üzerinden arama yapar ve oynatır. Masaüstü uygulaması yoksa veya hata alınırsa tarayıcı (YouTube) tabanlı oynatmaya yönlendirir.
- **`actions/calendar.py`**:
  - **İşlev**: `get_calendar_events`, `add_calendar_event`, `delete_calendar_event` fonksiyonlarını barındırır. Takvim etkinliklerini okur, ekler veya siler. İşletim sistemi macOS dışındaysa `json` tabanlı lokal takvim fallback'ine düşer.
- **`actions/reminders.py`**:
  - **İşlev**: `get_reminders` ve `add_reminder` fonksiyonlarını barındırır. Anımsatıcıları sorgular veya listelere yeni anımsatıcılar ekler.
- **`actions/open_app.py`**:
  - **İşlev**: `open_app(app_name)` fonksiyonunu içerir. Sisteme yüklü uygulamaları isimleriyle bulup platform bağımsız olarak (macOS'te `open`, Windows'ta `os.startfile`, Ubuntu'da `subprocess.Popen`) çalıştırır.
- **`actions/browser.py`**:
  - **İşlev**: `browser_control(action, url, query)` fonksiyonu. Varsayılan web tarayıcısı üzerinden bağlantıları açar, Google araması veya Youtube video araması yaptırır.
- **`actions/screen_vision.py`**:
  - **İşlev**: `analyze_screen(query, target)`. `ImageGrab` veya `screencapture` kullanarak ekranın bir görüntüsünü (veya aktif pencereyi) kaydeder ve AI Vision modelleriyle ekranda ne olduğunu analiz ettirir.
- **`actions/tts.py`**:
  - **İşlev**: `speak_text(text)`. Sistem üzerinden (Cross-Platform olarak `pyttsx3`, macOS için eski sürümlerde `say` vb.) metinleri sese dönüştürür.
- **`actions/sys_info.py`**:
  - **İşlev**: CPU, RAM, Disk, Pil, İnternet durumu, IP ve Zaman/Tarih gibi donanım/sistem bilgisini okur.
- **`actions/weather.py`**:
  - **İşlev**: Basit hava durumu verisi çekmek için istek atar.
- **`actions/health.py` & `actions/youtube_stats.py`**:
  - **İşlev**: (Şu an kullanım dışı veya opsiyonel) Apple Health verilerini ve YouTube kanalı (abone/izlenme) istatistiklerini getirir.

## Sistem Anayasası ve Kısıtlamaların Özeti
Asistanın temel prensipleri (hangi eylemi nasıl alacağı) tamamen **`core/prompt.txt`** dosyasında tanımlıdır. Buradaki direktiflere uyar.
Güvenlik açısından en büyük sınırlandırma **`actions/shell.py`** içindedir. Asistanın terminal kullanma yetkisi vardır, ancak dosya taşıma, silme, yetki değiştirme (sudo) veya sistemi kapatma komutları hard-coded olarak yasaklanmış durumdadır.
