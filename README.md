# DiskPulse

**Visual Linux disk space analyzer & safe cache cleaner** built with Python + Qt 6 (`PySide6`), featuring hover glow effects and **live Omarchy theme synchronization**.

[![License: MIT](https://img.shields.io/badge/License-MIT-7376b7.svg)](LICENSE)
[![Buy Me a Coffee](https://img.shields.io/badge/Support-Buy%20Me%20a%20Coffee-FFDD00?logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/aurorauap)

## Features
- Live disk usage hero bar (`used / total / free`) for `/home`.
- **Safe Cache Cleaner:** Detects Trash, image thumbnails, `pip`, `uv`, `npm`, `gradle`, `cargo`, `yay`/`paru`, and shows `pacman` cache size with 1-click safe cleanup (never touches user documents).
- **Largest Folders in Home:** Visual proportional bars with 1-click **Open in File Manager**.
- Adapts live to your active Omarchy theme (`colors.toml` + Hyprland rounding).

## Quick Start
```bash
git clone https://github.com/ilievi187/diskpulse.git
cd diskpulse
./run.sh
```

## License
[MIT License](LICENSE)
