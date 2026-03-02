"""SFTP file browser panel — browse, download, and upload files over SSH."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QFileDialog,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject


# ── Background workers ────────────────────────────────────────────────────────

class _ListWorker(QObject):
    done     = pyqtSignal(list)   # [(name, is_dir, size), …]
    error    = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, sftp, path: str) -> None:
        super().__init__()
        self._sftp = sftp
        self._path = path

    def run(self) -> None:
        try:
            entries = []
            for attr in self._sftp.listdir_attr(self._path):
                is_dir = hasattr(attr, "st_mode") and bool(attr.st_mode & 0o040000)
                entries.append((attr.filename, is_dir, attr.st_size or 0))
            entries.sort(key=lambda e: (not e[1], e[0].lower()))
            self.done.emit(entries)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class _TransferWorker(QObject):
    progress = pyqtSignal(int)   # bytes transferred so far
    done     = pyqtSignal()
    error    = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, sftp, remote: str, local: str, upload: bool) -> None:
        super().__init__()
        self._sftp   = sftp
        self._remote = remote
        self._local  = local
        self._upload = upload

    def run(self) -> None:
        try:
            cb = lambda sent, _total: self.progress.emit(sent)
            if self._upload:
                self._sftp.put(self._local, self._remote, callback=cb)
            else:
                self._sftp.get(self._remote, self._local, callback=cb)
            self.done.emit()
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class _ConnectWorker(QObject):
    ready    = pyqtSignal(object)   # SFTPClient
    error    = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, ssh_worker) -> None:
        super().__init__()
        self._ssh = ssh_worker

    def run(self) -> None:
        try:
            sftp = self._ssh.open_sftp()
            if sftp:
                self.ready.emit(sftp)
            else:
                self.error.emit("SFTP not available on this server.")
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


# ── Panel widget ──────────────────────────────────────────────────────────────

class SFTPPanel(QWidget):
    """
    Embedded SFTP file browser.

    Call connect_sftp(sftp_client) after the SSH session is established.
    The panel lists remote directories; double-clicking a file downloads it,
    double-clicking a folder navigates into it.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sftp    = None
        self._cwd     = "/"
        self._thread: Optional[QThread] = None
        self._worker  = None   # keep ref to prevent GC
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Header
        hdr = QHBoxLayout()
        hdr.addWidget(self._make_lbl("<b>SFTP</b>"))
        hdr.addStretch()
        self._btn_refresh = QPushButton("↻")
        self._btn_refresh.setFixedSize(24, 24)
        self._btn_refresh.setToolTip("Refresh")
        self._btn_refresh.setEnabled(False)
        self._btn_refresh.clicked.connect(self._refresh)
        hdr.addWidget(self._btn_refresh)
        layout.addLayout(hdr)

        # Path / navigation bar
        nav = QHBoxLayout()
        btn_up = QPushButton("↑")
        btn_up.setFixedSize(28, 24)
        btn_up.setToolTip("Parent directory")
        btn_up.clicked.connect(self._go_up)
        nav.addWidget(btn_up)
        self._path_lbl = QLabel("/")
        self._path_lbl.setStyleSheet("color: #888; font-size: 11px;")
        self._path_lbl.setWordWrap(False)
        nav.addWidget(self._path_lbl, 1)
        layout.addLayout(nav)

        # File list
        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget { background: #252526; color: #ccc; border: none; }"
            "QListWidget::item:selected { background: #094771; }"
            "QListWidget::item:hover { background: #2a2d2e; }"
        )
        self._list.itemDoubleClicked.connect(self._on_item_activated)
        self._list.currentItemChanged.connect(
            lambda cur, _: self._btn_dl.setEnabled(
                cur is not None
                and not cur.data(Qt.ItemDataRole.UserRole)   # not a dir
            )
        )
        layout.addWidget(self._list)

        # Transfer buttons
        btn_row = QHBoxLayout()
        self._btn_dl = QPushButton("⬇  Download")
        self._btn_dl.setEnabled(False)
        self._btn_dl.clicked.connect(self._on_download)
        btn_row.addWidget(self._btn_dl)

        self._btn_ul = QPushButton("⬆  Upload")
        self._btn_ul.setEnabled(False)
        self._btn_ul.clicked.connect(self._on_upload)
        btn_row.addWidget(self._btn_ul)
        layout.addLayout(btn_row)

        # Status
        self._status_lbl = QLabel("Not connected")
        self._status_lbl.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._status_lbl)

    @staticmethod
    def _make_lbl(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #ccc;")
        return lbl

    # ── Public API ────────────────────────────────────────────────────────────

    def connect_sftp(self, sftp) -> None:
        """Call after the SSH session is established (from any thread)."""
        self._sftp = sftp
        try:
            home = sftp.normalize(".")
            self._cwd = home
        except Exception:
            self._cwd = "/"
        self._btn_refresh.setEnabled(True)
        self._btn_ul.setEnabled(True)
        self._refresh()

    # ── Navigation ────────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        if not self._sftp:
            return
        self._list.clear()
        self._status_lbl.setText("Loading…")
        self._run_worker(
            _ListWorker(self._sftp, self._cwd),
            on_done=self._on_list_done,
            on_error=self._on_error,
        )

    def _on_list_done(self, entries: list) -> None:
        self._path_lbl.setText(self._cwd)
        self._list.clear()
        for name, is_dir, size in entries:
            icon  = "📁" if is_dir else "📄"
            extra = "" if is_dir else f"  ({_human(size)})"
            item  = QListWidgetItem(f"{icon}  {name}{extra}")
            item.setData(Qt.ItemDataRole.UserRole,     is_dir)
            item.setData(Qt.ItemDataRole.UserRole + 1, name)
            self._list.addItem(item)
        self._status_lbl.setText(f"{len(entries)} items")

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        is_dir = item.data(Qt.ItemDataRole.UserRole)
        if is_dir:
            name = item.data(Qt.ItemDataRole.UserRole + 1)
            self._cwd = str(PurePosixPath(self._cwd) / name)
            self._refresh()
        else:
            self._on_download()

    def _go_up(self) -> None:
        parent = str(PurePosixPath(self._cwd).parent)
        if parent != self._cwd:
            self._cwd = parent
            self._refresh()

    def _on_error(self, msg: str) -> None:
        self._status_lbl.setText(f"Error: {msg}")

    # ── File transfers ────────────────────────────────────────────────────────

    def _on_download(self) -> None:
        item = self._list.currentItem()
        if not item or not self._sftp:
            return
        name   = item.data(Qt.ItemDataRole.UserRole + 1)
        remote = str(PurePosixPath(self._cwd) / name)
        local, _ = QFileDialog.getSaveFileName(
            self, "Save File", str(Path.home() / name)
        )
        if not local:
            return
        self._status_lbl.setText(f"Downloading {name}…")
        w = _TransferWorker(self._sftp, remote, local, upload=False)
        w.done.connect(lambda: self._status_lbl.setText(f"Downloaded {name}"))
        self._run_worker(w, on_error=self._on_error)

    def _on_upload(self) -> None:
        if not self._sftp:
            return
        local, _ = QFileDialog.getOpenFileName(
            self, "Upload File", str(Path.home())
        )
        if not local:
            return
        name   = os.path.basename(local)
        remote = str(PurePosixPath(self._cwd) / name)
        self._status_lbl.setText(f"Uploading {name}…")
        w = _TransferWorker(self._sftp, remote, local, upload=True)
        w.done.connect(lambda: (
            self._status_lbl.setText(f"Uploaded {name}"),
            self._refresh(),
        ))
        self._run_worker(w, on_error=self._on_error)

    # ── Thread helper ─────────────────────────────────────────────────────────

    def _run_worker(self, worker, on_done=None, on_error=None) -> None:
        if self._thread and self._thread.isRunning():
            return
        self._worker = worker
        self._thread = QThread(self)
        worker.moveToThread(self._thread)
        self._thread.started.connect(worker.run)
        worker.finished.connect(self._thread.quit)
        if on_done and hasattr(worker, "done"):
            worker.done.connect(on_done)
        if on_error:
            worker.error.connect(on_error)
        self._thread.start()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _human(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size} {unit}"
        size //= 1024
    return f"{size} TB"
