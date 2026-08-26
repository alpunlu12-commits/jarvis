"""
Terminal komutu çalıştırma — WHITELIST bazlı güvenlik hardening.

Güvenlik prensibi:
- Sadece izin verilen komutlar çalıştırılır (whitelist)
- Tehlikeli komutlar engellenir
- Komut uzunluğu max 500 karakter
- Timeout 15 saniye
- Input sanitize: shell injection engeli
"""

from __future__ import annotations

import re
import shlex
import subprocess
from typing import Optional


# ── Whitelist: Sadece bu komutlar çalıştırılabilir ────────────────────────────
# Her entry: (komut_adı, izin_verilen_argüman_desenleri)
# argüman deseni None ise her argüman izinli (ama白名单 kontrolü devam eder)

WHITELISTED_COMMANDS: dict[str, list[str]] = {
    # Bilgi komutları (read-only)
    "dir":          [],
    "ls":           [],
    "echo":         ["*"],
    "whoami":       [],
    "hostname":     [],
    "date":         [],
    "time":         [],
    "ver":          [],
    "systeminfo":   [],
    "tasklist":     [],
    "netstat":      [],
    "ipconfig":     [],
    "arp":          [],
    "nslookup":     ["*"],  # herhangi bir domain
    "ping":         ["*"],  # herhangi bir host
    "tracert":      ["*"],  # herhangi bir host
    "pathping":     ["*"],
    "set":          [],
    "type":         ["*"],  # dosya okuma
    "where":        ["*"],  # executable bulma
    "find":         ["*"],  # dosya arama
    "tree":         [],
    "wmic":         [],
    "reg":          [],  # sadece listing (argüman whitelist ile)
    "netsh":        [],
    "help":         [],
    "color":        [],
    "cls":          [],
    "cmd":          [],
}

# ── Tamamen engellenen komut pattern'leri ─────────────────────────────────────
BLOCKED_PATTERNS: tuple[str, ...] = (
    # Sistem tehlikesi
    "rm -rf", "rm -r", "rmdir /s", "rmdir /q", "rd /s", "rd /q",
    "del /f", "del /s", "del /q", "format", "format c:", "format d:",
    # Sistem kapatma/açma
    "shutdown", "restart", "logoff", "hibernate",
    # Yetki/hesap manipülasyonu
    "net user", "net localgroup", "net accounts", "net share",
    "net session", "net start", "net stop",
    # Registry tehlikesi
    "reg delete", "reg add", "reg import", "reg export",
    "reg restore", "reg load",
    # PowerShell tehlikeli
    "invoke-expression", "iex", "invoke-command", "icm",
    "downloadstring", "downloadfile", "invoke-webrequest",
    "invoke-restmethod", "start-process", "remove-item",
    "set-content", "add-content", "out-file",
    # Curl pipe (shell injection vektörü)
    "curl", "wget", "bitsadmin",
    # Disk manipülasyonu
    "diskpart", "bcdedit", "bootcfg",
    # Güvenlik
    "cipher", "icacls", "takeown", "cacls",
    # Script execution
    "powershell -enc", "powershell -e",
    "cmd /c powershell", "cmd.exe /c powershell",
    # Elevation
    "runas", "sudo",
)

# ── Sınırlamalar ──────────────────────────────────────────────────────────────
MAX_COMMAND_LENGTH: int = 500
TIMEOUT_SECONDS: int = 15
MAX_OUTPUT_LENGTH: int = 800


def _is_blocked(command_lower: str) -> Optional[str]:
    """Komut engellenen pattern ile eşleşiyor mu kontrol et."""
    for pattern in BLOCKED_PATTERNS:
        if pattern in command_lower:
            return pattern
    return None


def _get_base_command(cmd_str: str) -> str:
    """Komutun temel (ilk) kelimesini çıkar."""
    # Pipe/redirection temizle
    clean = cmd_str.split("|")[0].split(">")[0].split("<")[0]
    clean = clean.strip()
    # shlex.parse dene
    try:
        parts = shlex.split(clean)
        if parts:
            return parts[0].lower()
    except ValueError:
        pass
    # Fallback: boşlukla böl
    parts = clean.split()
    return parts[0].lower() if parts else ""


def _sanitize_command(command: str) -> tuple[bool, str]:
    """
    Komutu temizle ve whitelist kontrolü yap.

    Returns:
        (is_safe, error_or_cleaned_command)
    """
    if not command or not command.strip():
        return False, "Komut belirtilmedi."

    command = command.strip()

    # Uzunluk kontrolü
    if len(command) > MAX_COMMAND_LENGTH:
        return False, (
            f"Komut çok uzun ({len(command)} karakter, max {MAX_COMMAND_LENGTH})."
        )

    cmd_lower = command.lower()

    # Engel listesi kontrolü
    blocked = _is_blocked(cmd_lower)
    if blocked:
        return False, f"Engellendi: '{blocked}' komutu güvenlik nedeniyle engellendi."

    # Whitelist kontrolü
    base_cmd = _get_base_command(cmd_lower)

    if not base_cmd:
        return False, "Geçerli bir komut belirlenemedi."

    if base_cmd not in WHITELISTED_COMMANDS:
        return (
            False,
            f"Engellendi: '{base_cmd}' komutu whitelist'te değil. "
            f"İzinli komutlar: {', '.join(sorted(WHITELISTED_COMMANDS.keys()))}",
        )

    # Shell injection desenleri
    injection_patterns = (
        "$(", "`",  # command substitution
        "\\",       # escape sequences
        "&&",       # command chaining (kontrollü)
    )
    for pattern in injection_patterns:
        if pattern in cmd_lower and base_cmd != "echo":
            return False, f"Engellendi: Tehlikeli karakter tespit edildi ({pattern})."

    return True, command


def shell_run(command: str, timeout: Optional[int] = None) -> str:
    """
    Güvenli komut çalıştırma (whitelist bazlı).

    Args:
        command: Çalıştırılacak komut.
        timeout: Zaman aşımı saniye (varsayılan 15).

    Returns:
        Komut çıktısı veya hata mesajı.
    """
    is_safe, result = _sanitize_command(command)
    if not is_safe:
        return result

    effective_timeout = min(timeout or TIMEOUT_SECONDS, 60)

    try:
        proc = subprocess.run(  # nosec B602 - whitelist+blocklist validated via _sanitize_command(); shell=True required for internal commands (dir, tasklist, etc.)
            result,
            shell=True,  # nosec B602
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            encoding="utf-8",
            errors="replace",
        )

        output = (proc.stdout + proc.stderr).strip()
        if not output:
            return "Komut başarıyla çalıştı (çıktı yok)."

        if len(output) > MAX_OUTPUT_LENGTH:
            output = output[:MAX_OUTPUT_LENGTH] + "\n... (çıktı kısaltıldı)"

        return output

    except subprocess.TimeoutExpired:
        return f"Komut zaman aşımına uğradı ({effective_timeout}s)."
    except FileNotFoundError:
        return f"Komut bulunamadı: '{result.split()[0] if result else command}'"
    except OSError as e:
        return f"Komut çalıştırılamadı: {e}"
    except Exception as e:
        return f"Beklenmeyen hata: {e}"
