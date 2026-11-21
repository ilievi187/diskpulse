"""DiskPulse backend — Linux disk space analyzer and safe user cache cleaner."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


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


def scan_top_home_folders(limit: int = 12) -> list[FolderEntry]:
    home = Path.home()
    candidates = [p for p in home.iterdir() if p.is_dir() and not p.is_symlink()]
    if not candidates:
        return []

    entries: list[FolderEntry] = []
    try:
        res = subprocess.run(
            ["du", "-sb", "--", *[str(p) for p in candidates]],
            capture_output=True,
            text=True,
            timeout=25,
        )
        for line in res.stdout.splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2 and parts[0].isdigit():
                p = Path(parts[1])
                entries.append(FolderEntry(name=p.name, path=p, size_bytes=int(parts[0])))
    except Exception:
        for p in candidates:
            entries.append(FolderEntry(name=p.name, path=p, size_bytes=_du_bytes(p)))

    entries.sort(key=lambda e: e.size_bytes, reverse=True)
    return entries[:limit]


def scan_safe_caches() -> list[CacheTarget]:
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
    for cid, title, desc, path, direct, hint in specs:
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
