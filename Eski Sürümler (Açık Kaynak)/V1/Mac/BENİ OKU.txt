YAPILIŞ VİDEOLARI:

Tutorial: https://youtu.be/6D136kF5dbs
Hata alırsan izle: https://youtube.com/shorts/k19F0_xqfM4

──────────────────────────────────────────
  GEREKSİNİMLER
──────────────────────────────────────────

  • macOS (sadece Mac'te çalışır)
  • Python 3 (macOS'ta genellikle yüklü gelir)
  • Homebrew (yoksa aşağıdaki adımı takip et)
  • Gemini API Anahtarı → https://aistudio.google.com
  • YouTube API Anahtarı (isteğe bağlı, sadece YouTube istatistik özelliği için)

──────────────────────────────────────────
  KURULUM
──────────────────────────────────────────

1. VS Code'u aç ve jarvis klasörünü içine sürükle
   (File → Open Folder → jarvis klasörünü seç)

2. Terminali aç: Ctrl+` (backtick tuşu)

3. Homebrew kurulu değilse terminale şunu yapıştır:
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   Kurulum bitince terminali kapat, yeni terminal aç.

4. Kurulum scriptini çalıştır:
   bash setup.sh

   Bu komut otomatik olarak şunları yapar:
   - PortAudio kurulumu (mikrofon için gerekli)
   - Python sanal ortamı oluşturma
   - Gerekli paketlerin yüklenmesi
   - Font kurulumu

5. Gemini API anahtarını al:
   - https://aistudio.google.com adresine git
   - "Get API Key" → "Create API Key"
   - Çıkan anahtarı kopyala

6. Kurulum bitince "Şimdi başlatılsın mı? (e/h)" sorusuna e yaz.
   İlk açılışta API anahtarını yapıştıracağın bir ekran çıkacak,
   oraya Gemini anahtarını yapıştır → Hazır!

──────────────────────────────────────────
  SONRADAN BAŞLATMA
──────────────────────────────────────────

  VS Code terminalinde:

  source venv/bin/activate
  python main.py

──────────────────────────────────────────
  KULLANIM
──────────────────────────────────────────

  • "Jarvis" diyerek sesli komut verin
  • Yazı kutusuna yazıp Enter'a basın
  • F4 veya Cmd+M ile mikrofonu susturun

──────────────────────────────────────────
