"""
Sistem sağlık skoru — CPU/RAM/Disk'e göre 0-100 arası skor.
"""

from __future__ import annotations

from typing import Optional

try:
    import psutil
    _HAS_PSUTIL: bool = True
except ImportError:
    _HAS_PSUTIL = False


def get_health_score(query: str = "overall") -> str:
    """
    Sistem sağlık skorunu hesapla.

    Args:
        query: overall/cpu/ram/disk/all

    Returns:
        Sağlık skoru ve detaylar.
    """
    if not _HAS_PSUTIL:
        return "psutil kurulu değil. Sağlık skoru hesaplanamadı."

    q = query.lower().strip()

    try:
        cpu_score = _score_cpu()
        ram_score = _score_ram()
        disk_score = _score_disk()
    except Exception as e:
        return f"Sağlık skoru hesaplanırken hata: {e}"

    if q == "cpu":
        return f"CPU sağlık skoru: {cpu_score}/100 — {_grade(cpu_score)}"
    if q == "ram":
        return f"RAM sağlık skoru: {ram_score}/100 — {_grade(ram_score)}"
    if q == "disk":
        return f"Disk sağlık skoru: {disk_score}/100 — {_grade(disk_score)}"

    # Overall: ağırlıklı ortalama
    overall = int(cpu_score * 0.4 + ram_score * 0.35 + disk_score * 0.25)
    grade = _grade(overall)

    lines = [
        f"🖥️ Sistem Sağlık Skoru: {overall}/100 — {grade}",
        f"  CPU:  {cpu_score}/100 ({_cpu_detail()})",
        f"  RAM:  {ram_score}/100 ({_ram_detail()})",
        f"  Disk: {disk_score}/100 ({_disk_detail()})",
        f"  Ağırlık: CPU %{40} | RAM %{35} | Disk %{25}",
    ]
    return "\n".join(lines)


def _score_cpu() -> int:
    """CPU sağlık skoru (0-100). Düşük kullanım = yüksek skor."""
    usage = psutil.cpu_percent(interval=0.5)
    # %0 kullanım = 100 skor, %100 kullanım = 0 skor
    score = max(0, min(100, int(100 - usage)))
    return score


def _score_ram() -> int:
    """RAM sağlık skoru (0-100). Düşük kullanım = yüksek skor."""
    vm = psutil.virtual_memory()
    score = max(0, min(100, int(100 - vm.percent)))
    return score


def _score_disk() -> int:
    """Disk sağlık skoru (0-100). Düşük kullanım = yüksek skor."""
    du = psutil.disk_usage("C:\\")
    score = max(0, min(100, int(100 - du.percent)))
    return score


def _cpu_detail() -> str:
    """CPU detayı."""
    usage = psutil.cpu_percent(interval=0.1)
    count = psutil.cpu_count(logical=True)
    freq = psutil.cpu_freq()
    freq_str = f", {freq.current:.0f}MHz" if freq else ""
    return f"%{usage:.1f} kullanım, {count} çekirdek{freq_str}"


def _ram_detail() -> str:
    """RAM detayı."""
    vm = psutil.virtual_memory()
    total = vm.total / (1024 ** 3)
    used = vm.used / (1024 ** 3)
    return f"{used:.1f}/{total:.1f}GB (%{vm.percent:.0f})"


def _disk_detail() -> str:
    """Disk detayı."""
    du = psutil.disk_usage("C:\\")
    total = du.total / (1024 ** 3)
    free = du.free / (1024 ** 3)
    return f"{free:.1f}GB boş / {total:.1f}GB toplam"


def _grade(score: int) -> str:
    """Skoru harf notuna çevir."""
    if score >= 90:
        return "Mükemmel"
    if score >= 75:
        return "İyi"
    if score >= 50:
        return "Orta"
    if score >= 25:
        return "Düşük"
    return "Kritik"
