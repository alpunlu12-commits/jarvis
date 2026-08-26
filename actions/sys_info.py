"""
Sistem bilgisi — psutil ile battery/cpu/ram/disk/time/date/network.
"""

from __future__ import annotations

import datetime
import subprocess
from typing import Optional

try:
    import psutil
    _HAS_PSUTIL: bool = True
except ImportError:
    _HAS_PSUTIL = False


def get_system_info(query: str = "all") -> str:
    """
    Sistem bilgisini sorguya göre döndür.

    Args:
        query: battery/cpu/ram/disk/time/date/network/all

    Returns:
        Biçimlendirilmiş sistem bilgisi.
    """
    q = query.lower().strip()
    results: list[str] = []

    dispatch: dict[str, callable] = {
        "battery": _battery, "pil": _battery,
        "cpu": _cpu, "işlemci": _cpu,
        "ram": _ram, "bellek": _ram, "memory": _ram,
        "disk": _disk, "depolama": _disk,
        "time": _time, "saat": _time, "zaman": _time,
        "date": _date, "tarih": _date,
        "network": _network, "ağ": _network, "wifi": _network,
    }

    if q == "all":
        for fn in dispatch.values():
            if fn not in [_time, _date] or True:
                results.append(fn())
    elif q in dispatch:
        results.append(dispatch[q]())
    else:
        valid = sorted(set(dispatch.keys()))
        return f"Bilinmeyen sorgu: '{q}'. Geçerli: {', '.join(valid)}"

    return "\n".join(r for r in results if r)


def _battery() -> str:
    """Pil durumu (psutil veya PowerShell fallback)."""
    if _HAS_PSUTIL:
        bat = psutil.sensors_battery()
        if bat:
            status = "Şarj oluyor" if bat.power_plugged else "Pilde"
            return f"Pil: %{bat.percent:.0f} — {status}"
    try:
        out = subprocess.check_output(
            ["powershell", "-Command",
             "Get-WmiObject Win32_Battery | "
             "Select-Object EstimatedChargeRemaining,BatteryStatus | "
             "ConvertTo-Json"],
            text=True, timeout=8, stderr=subprocess.DEVNULL,
        )
        import json
        data = json.loads(out.strip())
        if isinstance(data, list):
            data = data[0]
        pct = data.get("EstimatedChargeRemaining", "?")
        code = data.get("BatteryStatus", 0)
        status = "Şarj oluyor" if code in (2, 6, 7, 8, 9) else "Pilde"
        return f"Pil: %{pct} — {status}"
    except Exception:
        pass
    return "Pil bilgisi alınamadı (masaüstü olabilir)."


def _cpu() -> str:
    """CPU kullanımı ve bilgileri."""
    if not _HAS_PSUTIL:
        return "CPU bilgisi alınamadı (psutil kurulu değil)."
    usage = psutil.cpu_percent(interval=0.5)
    count = psutil.cpu_count(logical=True)
    freq = psutil.cpu_freq()
    freq_str = f", {freq.current:.0f} MHz" if freq else ""
    return f"CPU: %{usage:.1f} kullanım — {count} çekirdek{freq_str}"


def _ram() -> str:
    """RAM kullanımı."""
    if not _HAS_PSUTIL:
        return "RAM bilgisi alınamadı (psutil kurulu değil)."
    vm = psutil.virtual_memory()
    total = vm.total / (1024 ** 3)
    used = vm.used / (1024 ** 3)
    return f"RAM: {used:.1f}GB / {total:.1f}GB kullanımda (%{vm.percent:.0f})"


def _disk() -> str:
    """Disk kullanımı (C: drive)."""
    if _HAS_PSUTIL:
        du = psutil.disk_usage("C:\\")
        total = du.total / (1024 ** 3)
        used = du.used / (1024 ** 3)
        free = du.free / (1024 ** 3)
        return f"Disk (C:): {used:.1f}GB kullanıldı, {free:.1f}GB boş (toplam {total:.1f}GB)"
    try:
        out = subprocess.check_output(
            ["wmic", "logicaldisk", "get", "size,freespace,caption"],
            text=True, timeout=5,
        )
        lines = [l for l in out.strip().splitlines()
                 if l.strip() and "Caption" not in l]
        if lines:
            return f"Disk: {lines[0].strip()}"
    except Exception:
        pass
    return "Disk bilgisi alınamadı."


def _time() -> str:
    """Mevcut saat."""
    now = datetime.datetime.now()
    return f"Saat: {now.strftime('%H:%M:%S')}"


def _date() -> str:
    """Mevcut tarih."""
    now = datetime.datetime.now()
    return f"Tarih: {now.strftime('%d %B %Y, %A')}"


def _network() -> str:
    """Ağ bağlantısı (WiFi SSID veya IP)."""
    # WiFi SSID
    try:
        out = subprocess.check_output(
            ["netsh", "wlan", "show", "interfaces"],
            text=True, timeout=5, stderr=subprocess.DEVNULL,
            encoding="utf-8", errors="replace",
        )
        for line in out.splitlines():
            if "SSID" in line and "BSSID" not in line:
                ssid = line.split(":", 1)[-1].strip()
                if ssid:
                    return f"WiFi: {ssid} bağlı"
    except Exception:
        pass
    # IP fallback
    try:
        out = subprocess.check_output(
            ["ipconfig"],
            text=True, timeout=5,
            encoding="utf-8", errors="replace",
        )
        for line in out.splitlines():
            if "IPv4" in line:
                ip = line.split(":", 1)[-1].strip()
                if ip and not ip.startswith("169."):
                    return f"Ağ: IP {ip}"
    except Exception:
        pass
    return "Ağ bağlantısı bulunamadı."
