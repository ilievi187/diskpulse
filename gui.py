#!/usr/bin/env python3
"""DiskPulse — Visual Linux Disk Analyzer & Safe Cache Cleaner (Qt 6 / PySide6 + Live Omarchy Theme)."""

from __future__ import annotations

import sys

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QUrl, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import diskpulse as dp
from theme import ThemePalette, ThemeWatcher, build_stylesheet


class GlowButton(QPushButton):
    def __init__(self, text: str = "", glow_hex: str = "#7376b7", max_blur: float = 18.0, parent=None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._max_blur = max_blur
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setOffset(0, 0)
        self._shadow.setBlurRadius(0.0)
        self.update_glow_color(glow_hex)
        self.setGraphicsEffect(self._shadow)

        self._anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._anim.setDuration(170)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def update_glow_color(self, hex_color: str) -> None:
        c = QColor(hex_color)
        c.setAlpha(150)
        self._shadow.setColor(c)

    def enterEvent(self, event) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._shadow.blurRadius())
        self._anim.setEndValue(self._max_blur)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._shadow.blurRadius())
        self._anim.setEndValue(0.0)
        self._anim.start()
        super().leaveEvent(event)


class ScanWorker(QThread):
    scanned = Signal(object, object, object)

    def run(self) -> None:
        overview = dp.get_disk_overview()
        caches = dp.scan_safe_caches()
        folders = dp.scan_top_home_folders(12)
        self.scanned.emit(overview, caches, folders)


class DiskPulseWindow(QMainWindow):
    def __init__(self, watcher: ThemeWatcher) -> None:
        super().__init__()
        self.watcher = watcher
        self.palette_data: ThemePalette = watcher.palette
        self.overview: dp.DiskOverview | None = None
        self.caches: list[dp.CacheTarget] = []
        self.folders: list[dp.FolderEntry] = []
        self._worker: ScanWorker | None = None
        self._glow_buttons: list[GlowButton] = []

        self.setWindowTitle("DiskPulse — Linux Disk Analyzer & Cache Cleaner")
        self.resize(960, 680)
        self.setMinimumSize(760, 540)

        self._build_ui()
        self._bind_shortcuts()
        self.apply_theme(self.palette_data)
        self.watcher.theme_changed.connect(self.apply_theme)

        QTimer.singleShot(40, self.start_scan)

    def _btn(self, text: str, obj_name: str = "", blur: float = 16.0) -> GlowButton:
        b = GlowButton(text, glow_hex=self.palette_data.accent, max_blur=blur)
        if obj_name:
            b.setObjectName(obj_name)
        self._glow_buttons.append(b)
        return b

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(14)

        # Header + Disk Overview Card
        header_card = QFrame()
        header_card.setObjectName("HeaderCard")
        hc = QVBoxLayout(header_card)
        hc.setContentsMargins(20, 16, 20, 16)
        hc.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(14)
        logo = QLabel("◉")
        logo.setObjectName("LogoBadge")
        logo.setFixedSize(44, 44)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(logo)

        tcol = QVBoxLayout()
        tcol.setSpacing(2)
        t = QLabel("DiskPulse")
        t.setObjectName("TitleLabel")
        self.disk_sub = QLabel("Scanning Linux storage & safe caches...")
        self.disk_sub.setObjectName("SubtitleLabel")
        tcol.addWidget(t)
        tcol.addWidget(self.disk_sub)
        top.addLayout(tcol)
        top.addStretch()

        self.reclaim_pill = QLabel("0 B Reclaimable")
        self.reclaim_pill.setObjectName("StatPill")
        top.addWidget(self.reclaim_pill)

        self.rescan_btn = self._btn("↻  Rescan", obj_name="PrimaryButton", blur=20.0)
        self.rescan_btn.clicked.connect(self.start_scan)
        top.addWidget(self.rescan_btn)
        hc.addLayout(top)

        self.disk_bar = QProgressBar()
        self.disk_bar.setRange(0, 100)
        self.disk_bar.setFixedHeight(10)
        self.disk_bar.setTextVisible(False)
        hc.addWidget(self.disk_bar)
        root.addWidget(header_card)

        # Toast
        self.toast = QFrame()
        self.toast.setObjectName("ToastBanner")
        tl = QHBoxLayout(self.toast)
        tl.setContentsMargins(14, 8, 14, 8)
        self.toast_lbl = QLabel("")
        self.toast_lbl.setStyleSheet("font-weight: 600;")
        tl.addWidget(self.toast_lbl, 1)
        self.toast.hide()
        root.addWidget(self.toast)

        # Scrollable content
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.body_widget = QWidget()
        self.body_layout = QVBoxLayout(self.body_widget)
        self.body_layout.setContentsMargins(2, 2, 6, 6)
        self.body_layout.setSpacing(12)
        self.scroll.setWidget(self.body_widget)
        root.addWidget(self.scroll, 1)

        # Footer
        footer = QHBoxLayout()
        self.status_lbl = QLabel("Ready")
        self.status_lbl.setObjectName("SubtitleLabel")
        self.theme_lbl = QLabel("")
        self.theme_lbl.setObjectName("SubtitleLabel")
        support_btn = self._btn("☕  Support", obj_name="ChipButton", blur=14.0)
        support_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://buymeacoffee.com/aurorauap")))
        footer.addWidget(self.status_lbl)
        footer.addStretch()
        footer.addWidget(self.theme_lbl)
        footer.addWidget(support_btn)
        root.addLayout(footer)

    def _bind_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+R"), self, self.start_scan)
        QShortcut(QKeySequence("F5"), self, self.start_scan)
        QShortcut(QKeySequence("Ctrl+Q"), self, self.close)

    def apply_theme(self, palette: ThemePalette) -> None:
        self.palette_data = palette
        app = QApplication.instance()
        if app:
            extra = f"""
            QProgressBar {{
                background-color: {palette.bg};
                border: 1px solid {palette.border};
                border-radius: 5px;
            }}
            QProgressBar::chunk {{
                background-color: {palette.accent};
                border-radius: 4px;
            }}
            """
            app.setStyleSheet(build_stylesheet(palette) + extra)
        for b in self._glow_buttons:
            b.update_glow_color(palette.accent)
        self.theme_lbl.setText(f"{palette.source_name} ({palette.mode}) · {palette.accent}")
        self._render()

    def _show_toast(self, msg: str) -> None:
        self.toast_lbl.setText(msg)
        self.toast.show()
        QTimer.singleShot(4000, self.toast.hide)

    def start_scan(self) -> None:
        if self._worker is not None:
            return
        self.status_lbl.setText("Scanning home folders and caches...")
        self.rescan_btn.setEnabled(False)
        self._worker = ScanWorker()
        self._worker.scanned.connect(self._on_scanned)
        self._worker.start()

    def _on_scanned(self, overview: dp.DiskOverview, caches: list[dp.CacheTarget], folders: list[dp.FolderEntry]) -> None:
        self._worker = None
        self.rescan_btn.setEnabled(True)
        self.overview = overview
        self.caches = caches
        self.folders = folders

        self.disk_bar.setValue(int(overview.used_percent))
        self.disk_sub.setText(
            f"{dp.human_bytes(overview.used_bytes)} used of {dp.human_bytes(overview.total_bytes)} "
            f"· {dp.human_bytes(overview.free_bytes)} free ({overview.used_percent:.0f}%)"
        )
        reclaim = sum(c.size_bytes for c in caches if c.can_clean_directly)
        self.reclaim_pill.setText(f"{dp.human_bytes(reclaim)} Safe Cache")
        self.status_lbl.setText(f"Found {len(caches)} cache(s) and {len(folders)} top folders")
        self._render()

    def _render(self) -> None:
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        p = self.palette_data

        # Section 1: Safe Cache Cleaner
        c_title = QLabel("Safe Cache Cleaner")
        c_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        self.body_layout.addWidget(c_title)

        if not self.caches:
            lbl = QLabel("No large caches (>1 MB) found — your system is super clean!")
            lbl.setObjectName("SubtitleLabel")
            self.body_layout.addWidget(lbl)
        else:
            for target in self.caches:
                card = QFrame()
                card.setObjectName("JobCard")
                row = QHBoxLayout(card)
                row.setContentsMargins(16, 12, 16, 12)
                row.setSpacing(12)

                col = QVBoxLayout()
                col.setSpacing(2)
                t = QLabel(target.title)
                t.setStyleSheet("font-size: 14px; font-weight: 700;")
                d = QLabel(f"{target.description} · {target.path}")
                d.setObjectName("SubtitleLabel")
                col.addWidget(t)
                col.addWidget(d)
                row.addLayout(col, 1)

                sz = QLabel(dp.human_bytes(target.size_bytes))
                sz.setStyleSheet(f"color: {p.accent}; font-weight: 800; font-size: 14px;")
                row.addWidget(sz)

                if target.can_clean_directly:
                    clean_btn = GlowButton("Clean", glow_hex=p.danger, max_blur=14.0)
                    clean_btn.setObjectName("DangerAction")
                    clean_btn.clicked.connect(lambda checked=False, tg=target: self._clean_target(tg))
                    row.addWidget(clean_btn)
                else:
                    copy_btn = GlowButton("Copy Cmd", glow_hex=p.accent, max_blur=12.0)
                    copy_btn.setObjectName("CardAction")
                    copy_btn.clicked.connect(lambda checked=False, cmd=target.manual_hint: (QApplication.clipboard().setText(cmd), self._show_toast(f"Copied: {cmd}")))
                    row.addWidget(copy_btn)

                self.body_layout.addWidget(card)

        # Section 2: Largest Folders in Home
        f_title = QLabel("Largest Folders in Home")
        f_title.setStyleSheet("font-size: 15px; font-weight: 700; margin-top: 8px;")
        self.body_layout.addWidget(f_title)

        max_size = max((f.size_bytes for f in self.folders), default=1)
        for folder in self.folders:
            card = QFrame()
            card.setObjectName("JobCard")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 11, 16, 11)
            cl.setSpacing(6)

            top = QHBoxLayout()
            name = QLabel(folder.name)
            name.setStyleSheet("font-weight: 700; font-size: 13px;")
            sz = QLabel(dp.human_bytes(folder.size_bytes))
            sz.setStyleSheet(f"color: {p.fg_muted}; font-weight: 600;")
            open_btn = GlowButton("Open", glow_hex=p.accent, max_blur=10.0)
            open_btn.setObjectName("CardAction")
            open_btn.clicked.connect(lambda checked=False, fp=folder.path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(fp))))
            top.addWidget(name)
            top.addStretch()
            top.addWidget(sz)
            top.addWidget(open_btn)
            cl.addLayout(top)

            bar = QProgressBar()
            bar.setRange(0, 1000)
            bar.setValue(max(5, int(folder.size_bytes / max_size * 1000)))
            bar.setFixedHeight(6)
            bar.setTextVisible(False)
            cl.addWidget(bar)
            self.body_layout.addWidget(card)

        self.body_layout.addStretch()

    def _clean_target(self, target: dp.CacheTarget) -> None:
        reply = QMessageBox.question(
            self,
            "Confirm Cache Clean",
            f"Clear '{target.title}' ({dp.human_bytes(target.size_bytes)}) at:\n{target.path}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            freed = dp.clean_cache_target(target)
            self._show_toast(f"✓ Freed {dp.human_bytes(freed)} from {target.title}")
            self.start_scan()
        except Exception as exc:
            self._show_toast(f"Error: {exc}")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("DiskPulse")
    app.setDesktopFileName("diskpulse")
    watcher = ThemeWatcher(app)
    win = DiskPulseWindow(watcher)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
