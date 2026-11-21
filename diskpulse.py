"""DiskPulse backend — Linux disk space analyzer and safe user cache cleaner."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


@dataclass
class DiskOverview:
    mount: str
    total_bytes: int
    used_bytes: int
    free_bytes: int

    @property
    def used_percent(self) -> float:
        return (self.used_bytes / self.total_bytes * 100.0) if self.total_bytes > 0 else 0.0


@dataclass
class FolderEntry:
    name: str
    path: Path
    size_bytes: int


@dataclass
class CacheTarget:
    id: str
    title: str
    description: str
    path: Path
    size_bytes: int
    can_clean_directly: bool = True
    manual_hint: str = ""


def human_bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            return f"{size:.2f} {unit}" if unit in ("GB", "TB") else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{n} B"


def get_disk_overview() -> DiskOverview:
    u = shutil.disk_usage(Path.home())
    return DiskOverview(mount=str(Path.home()), total_bytes=u.total, used_bytes=u.used, free_bytes=u.free)


def _du_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        res = subprocess.run(["du", "-sb", str(path)], capture_output=True, text=True, timeout=15)
        if res.returncode == 0 and res.stdout.strip():
            return int(res.stdout.split()[0])
    except Exception:
        pass
    total = 0
    try:
        for p in path.rglob("*"):
            if p.is_file() and not p.is_symlink():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def scan_top_home_folders(
    limit: int = 12,
    on_progress: Optional[Callable[[int, str], None]] = None,
) -> list[FolderEntry]:
    home = Path.home()
    candidates = sorted(
        [p for p in home.iterdir() if p.is_dir() and not p.is_symlink()],
        key=lambda p: p.name.lower(),
    )
    if not candidates:
        return []

    entries: list[FolderEntry] = []
    total = len(candidates)
    for idx, folder in enumerate(candidates, start=1):
        if on_progress:
            pct = 35 + int((idx / total) * 63)
            on_progress(pct, f"Scanning folder {idx}/{total}: ~/{folder.name}")
        size = _du_bytes(folder)
        entries.append(FolderEntry(name=folder.name, path=folder, size_bytes=size))

    entries.sort(key=lambda e: e.size_bytes, reverse=True)
    if on_progress:
        on_progress(100, "Scan complete")
    return entries[:limit]


def scan_safe_caches(
    on_progress: Optional[Callable[[int, str], None]] = None,
) -> list[CacheTarget]:
    home = Path.home()
    specs = [
        ("trash", "Trash / Recycle Bin", "Deleted files waiting in your user Trash", home / ".local/share/Trash/files", True, ""),
        ("thumbs", "Image Thumbnails", "Cached desktop preview thumbnails (regenerated automatically)", home / ".cache/thumbnails", True, ""),
        ("pip", "Python pip Cache", "Downloaded Python wheel archives", home / ".cache/pip", True, ""),
        ("uv", "uv Python Cache", "Cached Python packages from uv", home / ".cache/uv", True, ""),
        ("npm", "Node / npm Cache", "Downloaded npm package tarballs", home / ".npm/_cacache", True, ""),
        ("gradle", "Gradle Build Cache", "Downloaded Gradle jars & build caches", home / ".gradle/caches", True, ""),
        ("cargo", "Rust Cargo Cache", "Downloaded Rust crate archives", home / ".cargo/registry/cache", True, ""),
        ("yay", "AUR Build Cache (yay)", "Old AUR source/package build directories", home / ".cache/yay", True, ""),
        ("paru", "AUR Build Cache (paru)", "Old AUR source/package build directories", home / ".cache/paru", True, ""),
        ("pacman", "Pacman Package Cache (root)", "Run `sudo pacman -Sc` in terminal to clean old packages", Path("/var/cache/pacman/pkg"), False, "sudo pacman -Sc"),
    ]

    found: list[CacheTarget] = []
    total = len(specs)
    for idx, (cid, title, desc, path, direct, hint) in enumerate(specs, start=1):
        if on_progress:
            pct = 5 + int((idx / total) * 30)
            on_progress(pct, f"Checking cache {idx}/{total}: {title}")
        if not path.exists():
            continue
        size = _du_bytes(path)
        if size > 1024 * 1024:  # Show caches > 1 MB
            found.append(CacheTarget(cid, title, desc, path, size, direct, hint))

    found.sort(key=lambda c: c.size_bytes, reverse=True)
    return found


def clean_cache_target(target: CacheTarget) -> int:
    """Safely clear contents inside a verified user cache directory. Returns bytes freed."""
    if not target.can_clean_directly:
        raise RuntimeError(f"Requires root privileges. Run: {target.manual_hint}")
    home = Path.home().resolve()
    resolved = target.path.resolve()
    if home not in resolved.parents:
        raise RuntimeError("Refusing to clean path outside user home directory.")

    before = target.size_bytes
    for child in list(resolved.iterdir()):
        try:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
        except OSError:
            pass
    after = _du_bytes(resolved)
    return max(0, before - after)
