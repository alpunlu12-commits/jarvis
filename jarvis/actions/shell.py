"""
Terminal komutu çalıştırma — macOS bash
Alp Ünlü tarafından yapılmıştır — @alppunlu
"""

import subprocess


# Tehlikeli komutları engelle
BLOCKED = [
    "rm -rf /",
    "sudo rm -rf",
    "mkfs",
    "dd if=",
    ":(){:|:&};:",
    "shutdown",
    "reboot",
    "halt",
    "diskutil erase",
    "diskutil apfs deletecontainer",
    ">:",
]


def shell_run(command: str, timeout: int = 30) -> str:
    if not command:
        return "Komut belirtilmedi."

    cmd_lower = command.lower()
    stripped = command.strip()

    if stripped.startswith(("rm ", "mv ", "cp ", "chmod ", "chown ", "sudo ")):
        return (
            "Güvenlik: Dosya veya yetki değiştiren komutlar doğrudan çalıştırılmıyor. "
            "Daha güvenli ve dar kapsamlı bir komut dene."
        )

    for blocked in BLOCKED:
        if blocked in cmd_lower:
            return f"Güvenlik: Bu komut engellendi → {blocked}"

    try:
        result = subprocess.run(
            command, shell=True, capture_output=True,
            text=True, timeout=timeout
        )
        output = (result.stdout + result.stderr).strip()
        if not output:
            return "Komut başarıyla çalıştı (çıktı yok)."
        # Çok uzun çıktıları kırp
        if len(output) > 800:
            output = output[:800] + "\n... (çıktı kısaltıldı)"
        return output
    except subprocess.TimeoutExpired:
        return f"Komut zaman aşımına uğradı ({timeout}s)."
    except Exception as e:
        return f"Hata: {e}"
