"""
Terminal komutu çalıştırma — Cross Platform (Özgür & Güvenli)
"""

import subprocess
import re

# Sadece ana komutları (ilk kelime) kontrol etmek için liste
BLOCKED_CMDS = {
    "mkfs", "fdisk", "cfdisk", "parted", "dd", "shutdown", 
    "reboot", "halt", "poweroff", "init", "format", "diskpart"
}

# Parametre bazlı özel tehlikeler (Örn: kök dizini silme)
BLOCKED_PATTERNS = [
    r"rm\s+-r[fv]*\s+/(?!\w)",  # 'rm -rf /' engeller, 'rm -rf /klasor' izin verir
    r"del\s+/s\s+/q\s+[c-zC-Z]:\\", # Windows C:\ kök silme
    r":\(\)\{:\|:&\}\;:"        # Fork bomb
]

def shell_run(command: str, timeout: int = 30) -> str:
    if not command:
        return "Komut belirtilmedi."

    stripped = command.strip()
    
    # 1. Komutun sadece ilk kelimesini al (Örn: "format C:" -> "format")
    first_word = stripped.split()[0].lower() if stripped else ""
    if first_word in BLOCKED_CMDS:
        return f"Güvenlik: Bu kök komut engellendi → {first_word}"

    # 2. Tehlikeli desenleri Regex ile kontrol et
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, stripped, re.IGNORECASE):
            return "Güvenlik: Yıkıcı bir işlem deseni algılandı."

    # Dosya okuma, yazma, taşıma, silme işlemleri tamamen serbest
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True,
            text=True, timeout=timeout
        )
        output = (result.stdout + result.stderr).strip()
        
        if not output:
            return "Komut başarıyla çalıştı (çıktı yok)."
            
        # Çok uzun çıktıları kırp (AI bağlamı kaybetmesin diye 2000 idealdir)
        if len(output) > 2000:
            output = output[:2000] + "\n... (çıktı kısaltıldı)"
            
        return output
    except subprocess.TimeoutExpired:
        return f"Komut zaman aşımına uğradı ({timeout}s)."
    except Exception as e:
        return f"Hata: {e}"
