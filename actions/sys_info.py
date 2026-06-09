
"""
Sistem bilgisi — cross-platform psutil + subprocess
"""

import subprocess
import sys
import platform
import os
import datetime
import socket

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def sys_info(query: str) -> str:
    query = query.lower().strip()

    results = []

    if query in ("battery", "pil", "all"):
        results.append(_battery())

    if query in ("cpu", "işlemci", "all"):
        results.append(_cpu())

    if query in ("ram", "bellek", "memory", "all"):
        results.append(_ram())

    if query in ("disk", "depolama", "all"):
        results.append(_disk())

    if query in ("time", "saat", "zaman", "all"):
        now = datetime.datetime.now()
        results.append(f"Saat: {now.strftime('%H:%M:%S')}")

    if query in ("date", "tarih", "all"):
        now = datetime.datetime.now()
        results.append(f"Tarih: {now.strftime('%d %B %Y, %A')}")

    if query in ("network", "ağ", "wifi", "all"):
        results.append(_network())

    if not results:
        results.append(f"Bilinmeyen sorgu: {query}. battery/cpu/ram/disk/time/date/network/all kullanın.")

    return "\n".join(r for r in results if r)


def _battery() -> str:
    if HAS_PSUTIL:
        bat = psutil.sensors_battery()
        if bat:
            status = "Şarj oluyor" if bat.power_plugged else "Pilde"
            return f"Pil: %{bat.percent:.0f} — {status}"

    if sys.platform == "darwin":
        try:
            out = subprocess.check_output(["pmset", "-g", "batt"], text=True, timeout=5)
            for line in out.splitlines():
                if "%" in line:
                    return f"Pil: {line.strip()}"
        except Exception:
            pass
    elif sys.platform == "win32":
        try:
            out = subprocess.check_output(["wmic", "path", "Win32_Battery", "get", "EstimatedChargeRemaining"], text=True, timeout=5)
            for line in out.splitlines():
                if line.strip().isdigit():
                    return f"Pil: %{line.strip()}"
        except Exception:
            pass
    elif sys.platform.startswith("linux"):
        try:
            out = subprocess.check_output(["upower", "-i", "$(upower -e | grep BAT | head -n 1)"], text=True, timeout=5, shell=True)
            for line in out.splitlines():
                if "percentage:" in line:
                    return f"Pil: {line.split(':')[1].strip()}"
        except Exception:
            pass

    return "Pil bilgisi alınamadı."


def _cpu() -> str:
    if HAS_PSUTIL:
        usage = psutil.cpu_percent(interval=0.5)
        count = psutil.cpu_count(logical=True)
        freq  = psutil.cpu_freq()
        freq_str = f", {freq.current:.0f} MHz" if freq else ""
        return f"CPU: %{usage:.1f} kullanım — {count} çekirdek{freq_str}"

    if sys.platform == "darwin":
        try:
            out = subprocess.check_output(["top", "-l", "1", "-n", "0", "-s", "0"], text=True, timeout=5)
            for line in out.splitlines():
                if "CPU usage" in line:
                    return f"CPU: {line.strip()}"
        except Exception:
            pass
    return "CPU bilgisi alınamadı."


def _ram() -> str:
    if HAS_PSUTIL:
        vm = psutil.virtual_memory()
        total = vm.total / (1024**3)
        used  = vm.used  / (1024**3)
        pct   = vm.percent
        return f"RAM: {used:.1f}GB / {total:.1f}GB kullanımda (%{pct:.0f})"
    return "RAM bilgisi alınamadı."


def _disk() -> str:
    if HAS_PSUTIL:
        du = psutil.disk_usage("/")
        total = du.total / (1024**3)
        used  = du.used  / (1024**3)
        free  = du.free  / (1024**3)
        return f"Disk (/): {used:.1f}GB kullanıldı, {free:.1f}GB boş (toplam {total:.1f}GB)"
    try:
        out = subprocess.check_output(["df", "-h", "/" if sys.platform != "win32" else "C:\\"], text=True, timeout=5)
        lines = out.strip().splitlines()
        if len(lines) >= 2:
            return f"Disk: {lines[1]}"
    except Exception:
        pass
    return "Disk bilgisi alınamadı."


def _network() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return f"Ağ: IP {ip}"
    except Exception:
        pass

    if sys.platform == "darwin":
        try:
            out = subprocess.check_output(
                ["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-I"],
                text=True, timeout=5, stderr=subprocess.DEVNULL)
            for line in out.splitlines():
                if " SSID:" in line:
                    ssid = line.split("SSID:")[-1].strip()
                    return f"WiFi: {ssid} bağlı"
        except Exception:
            pass
    return "Ağ bağlantısı bulunamadı."
