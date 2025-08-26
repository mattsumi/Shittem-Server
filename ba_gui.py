#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Blue Archive – Local Admin GUI

• Starts/stops mitmdump with blue_archive_addon.py
• Flip/unflip traffic via the addon's control server
• Send in-game mail, post notices, and edit account data against the private C# API
• Live logs for both mitmdump and the C# API (if you choose to launch it from here)

This file is a standalone launcher. Run it directly:

    python ba_admin_gui.py

Requirements: PySide6 (pip install pyside6)

Notes
-----
- Admin endpoints are addressed at the private server (default http://127.0.0.1:7000).
  If your server uses different routes, adjust AdminClient below.
- Flip/unflip hits the mitm addon's control server (default http://127.0.0.1:9080).
- All network calls time out quickly and report errors inline.
"""

from __future__ import annotations
import sys
import os
import json
import time
import typing as t
import subprocess
import threading
import shutil
import shlex
from dataclasses import dataclass
from urllib import request, parse, error

from PySide6 import QtCore, QtGui, QtWidgets

# -----------------------------
# HTTP Helper
# -----------------------------

class HttpError(RuntimeError):
    pass

class Http:
    def __init__(self, base_url: str, timeout: float = 6.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _build(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def get_json(self, path: str, headers: dict[str, str] | None = None) -> t.Any:
        url = self._build(path)
        req = request.Request(url, headers={"Accept": "application/json", **(headers or {})})
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                data = resp.read()
                ctype = resp.headers.get("content-type", "")
                if "json" not in ctype:
                    return data.decode("utf-8", errors="replace")
                return json.loads(data.decode("utf-8", errors="replace"))
        except error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise HttpError(f"GET {url} -> {e.code}: {body}")
        except Exception as e:
            raise HttpError(f"GET {url} failed: {e}")

    def post_json(self, path: str, payload: t.Any, headers: dict[str, str] | None = None) -> t.Any:
        url = self._build(path)
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=data, method="POST",
                              headers={"Content-Type": "application/json", "Accept": "application/json",
                                       **(headers or {})})
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                ctype = resp.headers.get("content-type", "")
                if "json" not in ctype:
                    return raw.decode("utf-8", errors="replace")
                return json.loads(raw.decode("utf-8", errors="replace"))
        except error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise HttpError(f"POST {url} -> {e.code}: {body}")
        except Exception as e:
            raise HttpError(f"POST {url} failed: {e}")

# -----------------------------
# Admin Client (adjust routes here to fit your server)
# -----------------------------

@dataclass
class AdminConfig:
    private_base: str = "http://127.0.0.1:7000"
    control_base: str = "http://127.0.0.1:9080"

class AdminClient:
    def __init__(self, cfg: AdminConfig):
        self.cfg = cfg
        self.http_private = Http(cfg.private_base)
        self.http_control = Http(cfg.control_base)

    # ---- MITM controls ----
    def flip(self) -> str:
        # blue_archive_addon.py exposes /_proxy/flip and /_proxy/unflip
        try:
            return self.http_control.get_json("/_proxy/flip") or "OK"
        except HttpError as e:
            return str(e)

    def unflip(self) -> str:
        try:
            return self.http_control.get_json("/_proxy/unflip") or "OK"
        except HttpError as e:
            return str(e)

    # ---- Admin operations on private API ----
    # If your server uses different endpoints, update these paths.

    def send_mail(self, account_id: int, subject: str, body: str,
                  attachments: list[dict[str, t.Any]] | None = None) -> t.Any:
        payload = {
            "accountId": account_id,
            "subject": subject,
            "body": body,
            "attachments": attachments or [],
        }
        return self.http_private.post_json("/admin/mail", payload)

    def post_notice(self, title: str, text: str,
                    starts_at: str | None = None, ends_at: str | None = None,
                    priority: int = 1) -> t.Any:
        payload = {
            "title": title,
            "text": text,
            "startsAt": starts_at,
            "endsAt": ends_at,
            "priority": priority,
        }
        return self.http_private.post_json("/admin/notice", payload)

    def get_account(self, account_id: int) -> t.Any:
        return self.http_private.get_json(f"/admin/account/{account_id}")

    def patch_account(self, account_id: int, patch: dict[str, t.Any]) -> t.Any:
        return self.http_private.post_json(f"/admin/account/{account_id}", patch)

# -----------------------------
# Process Runner (mitmdump / dotnet)
# -----------------------------

def build_mitmdump_cmd(executable_text: str, args: list[str]) -> list[str] | str:
    """
    Resolve mitmdump on Windows and choose the proper invocation:
    - If mitmdump resolves to .bat/.cmd => return a single command string (shell=True)
    - If it's an .exe/.com => return argv list (shell=False)
    - If not found => fall back to 'python -m mitmproxy.tools.main mitmdump' (shell=True)
    On non-Windows, we just return argv list.
    """
    path = shutil.which(executable_text) or executable_text
    lower = path.lower()
    if os.name == "nt":
        if lower.endswith((".bat", ".cmd")):
            # Batch files require the shell. Build a single string.
            return " ".join([f'"{path}"', *[shlex.quote(a) for a in args]])
        if lower.endswith((".exe", ".com")):
            return [path, *args]
        # If we can't be sure it's runnable directly, use the Python module entry.
        py = sys.executable
        return " ".join([f'"{py}"', "-m", "mitmproxy.tools.main", "mitmdump", *[shlex.quote(a) for a in args]])
    # POSIX: argv is fine
    return [path, *args]

class ProcessRunner(QtCore.QObject):
    output = QtCore.Signal(str)
    stopped = QtCore.Signal()

    def __init__(self, cmd: list[str] | str, cwd: str | None = None, env: dict[str, str] | None = None):
        super().__init__()
        self.cmd = cmd
        self.cwd = cwd
        self.env = env or os.environ.copy()
        self.proc: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self):
        if self.proc and self.proc.poll() is None:
            return
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW
        self.proc = subprocess.Popen(
            self.cmd,
            cwd=self.cwd,
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            shell=isinstance(self.cmd, str),  # string => likely needs shell (e.g., .bat/.cmd)
            creationflags=creationflags,
        )
        self._stop.clear()
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self):
        if not self.proc or not self.proc.stdout:
            return
        for line in self.proc.stdout:
            if self._stop.is_set():
                break
            self.output.emit(line.rstrip("\n"))
        self.stopped.emit()

    def terminate(self):
        self._stop.set()
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass

# -----------------------------
# UI Widgets
# -----------------------------

class LabeledLine(QtWidgets.QWidget):
    def __init__(self, label: str, placeholder: str = "", parent=None):
        super().__init__(parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.lbl = QtWidgets.QLabel(label)
        self.edit = QtWidgets.QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        lay.addWidget(self.lbl)
        lay.addWidget(self.edit, 1)

    def text(self) -> str:
        return self.edit.text().strip()

    def setText(self, s: str):
        self.edit.setText(s)

class PrettyButton(QtWidgets.QPushButton):
    def __init__(self, text: str, icon: QtGui.QIcon | None = None, parent=None):
        super().__init__(text, parent)
        if icon:
            self.setIcon(icon)
        self.setMinimumHeight(36)
        self.setCursor(QtCore.Qt.PointingHandCursor)

# ---- Mail Tab ----

class MailTab(QtWidgets.QWidget):
    def __init__(self, admin: AdminClient, parent=None):
        super().__init__(parent)
        self.admin = admin

        main = QtWidgets.QVBoxLayout(self)
        grid = QtWidgets.QGridLayout()
        self.account = LabeledLine("Account ID:", "3218642")
        self.subject = LabeledLine("Subject:", "Welcome!")
        self.body = QtWidgets.QPlainTextEdit()
        self.body.setPlaceholderText("Message body…")
        self.body.setMinimumHeight(120)

        grid.addWidget(self.account.lbl, 0, 0)
        grid.addWidget(self.account.edit, 0, 1)
        grid.addWidget(self.subject.lbl, 1, 0)
        grid.addWidget(self.subject.edit, 1, 1)
        grid.addWidget(QtWidgets.QLabel("Body:"), 2, 0)
        grid.addWidget(self.body, 2, 1)

        # Attachments table
        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ItemId", "Count", "Note"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked | QtWidgets.QAbstractItemView.EditKeyPressed)

        btns = QtWidgets.QHBoxLayout()
        add = PrettyButton("Add Attachment")
        rem = PrettyButton("Remove Selected")
        send = PrettyButton("Send Mail")
        btns.addWidget(add)
        btns.addWidget(rem)
        btns.addStretch(1)
        btns.addWidget(send)

        add.clicked.connect(self._add_row)
        rem.clicked.connect(self._remove_selected)
        send.clicked.connect(self._send)

        main.addLayout(grid)
        main.addWidget(self.table, 1)
        main.addLayout(btns)

    def _add_row(self):
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c in range(3):
            self.table.setItem(r, c, QtWidgets.QTableWidgetItem(""))

    def _remove_selected(self):
        for idx in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(idx)

    def _send(self):
        try:
            account_id = int(self.account.text())
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "Input error", "Account ID must be an integer")
            return
        subject = self.subject.text()
        body = self.body.toPlainText()
        attachments = []
        for r in range(self.table.rowCount()):
            item_id = self.table.item(r, 0)
            count = self.table.item(r, 1)
            note = self.table.item(r, 2)
            if item_id and count and item_id.text().strip() and count.text().strip():
                try:
                    attachments.append({
                        "itemId": int(item_id.text().strip()),
                        "count": int(count.text().strip()),
                        "note": (note.text().strip() if note else ""),
                    })
                except ValueError:
                    pass
        try:
            resp = self.admin.send_mail(account_id, subject, body, attachments)
            QtWidgets.QMessageBox.information(self, "Mail", f"Sent!\n\n{json.dumps(resp, indent=2)}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Mail failed", str(e))

# ---- Notice Tab ----

class NoticeTab(QtWidgets.QWidget):
    def __init__(self, admin: AdminClient, parent=None):
        super().__init__(parent)
        self.admin = admin
        main = QtWidgets.QFormLayout(self)
        self.title = QtWidgets.QLineEdit()
        self.text = QtWidgets.QPlainTextEdit()
        self.text.setPlaceholderText("Notice text… Markdown/plain supported by your server.")
        self.text.setMinimumHeight(140)
        self.start = QtWidgets.QDateTimeEdit(QtCore.QDateTime.currentDateTime())
        self.start.setCalendarPopup(True)
        self.end = QtWidgets.QDateTimeEdit(QtCore.QDateTime.currentDateTime().addDays(7))
        self.end.setCalendarPopup(True)
        self.priority = QtWidgets.QSpinBox()
        self.priority.setRange(0, 9)
        self.priority.setValue(1)
        btn = PrettyButton("Publish Notice")
        btn.clicked.connect(self._publish)

        main.addRow("Title:", self.title)
        main.addRow("Text:", self.text)
        main.addRow("Starts:", self.start)
        main.addRow("Ends:", self.end)
        main.addRow("Priority:", self.priority)
        main.addRow("", btn)

    def _publish(self):
        try:
            resp = self.admin.post_notice(
                self.title.text().strip(),
                self.text.toPlainText(),
                self.start.dateTime().toString(QtCore.Qt.ISODate),
                self.end.dateTime().toString(QtCore.Qt.ISODate),
                self.priority.value(),
            )
            QtWidgets.QMessageBox.information(self, "Notice", f"Published!\n\n{json.dumps(resp, indent=2)}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Publish failed", str(e))

# ---- Account Tab ----

class AccountTab(QtWidgets.QWidget):
    def __init__(self, admin: AdminClient, parent=None):
        super().__init__(parent)
        self.admin = admin
        v = QtWidgets.QVBoxLayout(self)
        top = QtWidgets.QHBoxLayout()
        self.account = LabeledLine("Account ID:", "3218642")
        fetch = PrettyButton("Fetch")
        save = PrettyButton("Save JSON")
        top.addWidget(self.account)
        top.addWidget(fetch)
        top.addStretch(1)
        top.addWidget(save)

        self.json_edit = QtWidgets.QPlainTextEdit()
        self.json_edit.setPlaceholderText("Account JSON will appear here… Edit and click Save JSON.")
        self.json_edit.setMinimumHeight(240)
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.json_edit.setFont(font)

        quick = QtWidgets.QGroupBox("Quick Edit")
        form = QtWidgets.QFormLayout(quick)
        self.level = QtWidgets.QSpinBox(); self.level.setRange(1, 999)
        self.pyroxene = QtWidgets.QSpinBox(); self.pyroxene.setRange(0, 10_000_000)
        self.credits = QtWidgets.QSpinBox(); self.credits.setRange(0, 10_000_000)
        apply_btn = PrettyButton("Apply Quick Fields")
        form.addRow("Level:", self.level)
        form.addRow("Pyroxene:", self.pyroxene)
        form.addRow("Credits:", self.credits)
        form.addRow("", apply_btn)

        apply_btn.clicked.connect(self._apply_quick)
        fetch.clicked.connect(self._fetch)
        save.clicked.connect(self._save)

        v.addLayout(top)
        v.addWidget(self.json_edit, 1)
        v.addWidget(quick)

    def _fetch(self):
        try:
            account_id = int(self.account.text())
            data = self.admin.get_account(account_id)
            self.json_edit.setPlainText(json.dumps(data, indent=2))
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Fetch failed", str(e))

    def _save(self):
        try:
            account_id = int(self.account.text())
            data = json.loads(self.json_edit.toPlainText())
            resp = self.admin.patch_account(account_id, data)
            QtWidgets.QMessageBox.information(self, "Saved", f"{json.dumps(resp, indent=2)}")
        except json.JSONDecodeError as e:
            QtWidgets.QMessageBox.warning(self, "JSON error", f"{e}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Save failed", str(e))

    def _apply_quick(self):
        patch = {}
        if self.level.value():
            patch["Level"] = self.level.value()
        patch["Pyroxene"] = self.pyroxene.value()
        patch["Credits"] = self.credits.value()
        try:
            account_id = int(self.account.text())
            resp = self.admin.patch_account(account_id, patch)
            QtWidgets.QMessageBox.information(self, "Patched", f"{json.dumps(resp, indent=2)}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Patch failed", str(e))

# ---- Server / MITM Tab ----

class ServerTab(QtWidgets.QWidget):
    def __init__(self, admin: AdminClient, parent=None):
        super().__init__(parent)
        self.admin = admin
        self.mitm_runner: ProcessRunner | None = None
        self.dotnet_runner: ProcessRunner | None = None

        v = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        self.private_url = QtWidgets.QLineEdit(admin.cfg.private_base)
        self.control_url = QtWidgets.QLineEdit(admin.cfg.control_base)
        self.mitmdump = QtWidgets.QLineEdit("mitmdump")
        self.addon = QtWidgets.QLineEdit("blue_archive_addon.py")
        self.listen_host = QtWidgets.QLineEdit("127.0.0.1")
        self.listen_port = QtWidgets.QLineEdit("9443")
        self.dotnet_dir = QtWidgets.QLineEdit("")

        form.addRow("Private API Base:", self.private_url)
        form.addRow("Control Server Base:", self.control_url)
        form.addRow("mitmdump:", self.mitmdump)
        form.addRow("Addon path:", self.addon)
        form.addRow("Listen host:", self.listen_host)
        form.addRow("Listen port:", self.listen_port)
        form.addRow("C# API directory (optional):", self.dotnet_dir)

        h = QtWidgets.QHBoxLayout()
        self.start_mitm = PrettyButton("Start MITM")
        self.stop_mitm = PrettyButton("Stop MITM")
        self.flip_btn = PrettyButton("Flip Traffic")
        self.unflip_btn = PrettyButton("Unflip Traffic")
        self.start_dotnet = PrettyButton("Start C# API")
        self.stop_dotnet = PrettyButton("Stop C# API")
        h.addWidget(self.start_mitm)
        h.addWidget(self.stop_mitm)
        h.addStretch(1)
        h.addWidget(self.flip_btn)
        h.addWidget(self.unflip_btn)
        h.addStretch(1)
        h.addWidget(self.start_dotnet)
        h.addWidget(self.stop_dotnet)

        self.log = QtWidgets.QPlainTextEdit(); self.log.setReadOnly(True)
        self.log.setMinimumHeight(200)
        self.log.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))

        self.start_mitm.clicked.connect(self._start_mitm)
        self.stop_mitm.clicked.connect(self._stop_mitm)
        self.flip_btn.clicked.connect(self._flip)
        self.unflip_btn.clicked.connect(self._unflip)
        self.start_dotnet.clicked.connect(self._start_dotnet)
        self.stop_dotnet.clicked.connect(self._stop_dotnet)

        v.addLayout(form)
        v.addLayout(h)
        v.addWidget(self.log)

    def _append(self, line: str):
        self.log.appendPlainText(line)

    def _start_mitm(self):
        # Build mitmdump argv (without the binary itself)
        args = [
            "--mode", "local:BlueArchive",
            "-s", self.addon.text().strip() or "blue_archive_addon.py",
            "--listen-host", self.listen_host.text().strip() or "127.0.0.1",
            "--listen-port", self.listen_port.text().strip() or "9443",
            "--set", "http2=true",
            "--set", "block_global=false",
        ]
        exe_text = self.mitmdump.text().strip() or "mitmdump"
        cmd = build_mitmdump_cmd(exe_text, args)
        self.mitm_runner = ProcessRunner(cmd)
        self.mitm_runner.output.connect(self._append)
        self.mitm_runner.stopped.connect(lambda: self._append("[mitmdump] stopped"))
        self.mitm_runner.start()
        self._append("[mitmdump] started")

    def _stop_mitm(self):
        if self.mitm_runner:
            self.mitm_runner.terminate()
            self._append("[mitmdump] terminating…")

    def _flip(self):
        msg = self.admin.flip()
        self._append(f"[flip] {msg}")

    def _unflip(self):
        msg = self.admin.unflip()
        self._append(f"[unflip] {msg}")

    def _start_dotnet(self):
        path = self.dotnet_dir.text().strip()
        if not path:
            QtWidgets.QMessageBox.information(self, "C# API", "Provide the project directory to run 'dotnet run'.")
            return
        cmd = ["dotnet", "run"]
        self.dotnet_runner = ProcessRunner(cmd, cwd=path)
        self.dotnet_runner.output.connect(lambda s: self._append(f"[dotnet] {s}"))
        self.dotnet_runner.stopped.connect(lambda: self._append("[dotnet] stopped"))
        self.dotnet_runner.start()
        self._append("[dotnet] starting…")

    def _stop_dotnet(self):
        if self.dotnet_runner:
            self.dotnet_runner.terminate()
            self._append("[dotnet] terminating…")

# ---- Logs-only Tab ----

class LogsTab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        v = QtWidgets.QVBoxLayout(self)
        self.view = QtWidgets.QPlainTextEdit(); self.view.setReadOnly(True)
        self.view.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))
        v.addWidget(self.view)

    def append(self, line: str):
        self.view.appendPlainText(line)

# -----------------------------
# Main Window
# -----------------------------

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Blue Archive – Admin Console")
        self.resize(1080, 720)
        self.setWindowIcon(QtGui.QIcon.fromTheme("applications-games"))

        # Global config + client
        cfg = AdminConfig()
        self.admin = AdminClient(cfg)

        # Tabs
        tabs = QtWidgets.QTabWidget()
        tabs.setDocumentMode(True)
        tabs.setTabPosition(QtWidgets.QTabWidget.North)
        tabs.setMovable(True)
        self.mail_tab = MailTab(self.admin)
        self.notice_tab = NoticeTab(self.admin)
        self.account_tab = AccountTab(self.admin)
        self.server_tab = ServerTab(self.admin)
        self.logs_tab = LogsTab()

        tabs.addTab(self.mail_tab, "📬 Mail")
        tabs.addTab(self.notice_tab, "📣 Notices")
        tabs.addTab(self.account_tab, "👤 Account")
        tabs.addTab(self.server_tab, "🖧 Server / MITM")
        tabs.addTab(self.logs_tab, "📝 Logs")

        self.setCentralWidget(tabs)
        self._apply_theme()

    def _apply_theme(self):
        # Simple pleasant dark theme
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor(26, 28, 35))
        pal.setColor(QtGui.QPalette.WindowText, QtCore.Qt.white)
        pal.setColor(QtGui.QPalette.Base, QtGui.QColor(33, 36, 44))
        pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(42, 45, 55))
        pal.setColor(QtGui.QPalette.Text, QtCore.Qt.white)
        pal.setColor(QtGui.QPalette.Button, QtGui.QColor(45, 48, 58))
        pal.setColor(QtGui.QPalette.ButtonText, QtCore.Qt.white)
        pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor(87, 154, 255))
        pal.setColor(QtGui.QPalette.HighlightedText, QtCore.Qt.black)
        self.setPalette(pal)

        # Removed unsupported CSS 'filter' to avoid "Unknown property filter" warnings.
        self.setStyleSheet(
            """
            QTabWidget::pane { border: 1px solid #444; }
            QTabBar::tab { background: #2b2f3a; padding: 8px 16px; border-top-left-radius: 8px; border-top-right-radius: 8px; }
            QTabBar::tab:selected { background: #3a3f4d; }
            QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #2f6be6, stop:1 #1f4fb8); color: white; border-radius: 10px; padding: 8px 16px; }
            QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #3a79ff, stop:1 #285fce); }
            QLineEdit, QPlainTextEdit, QSpinBox, QDateTimeEdit { background: #2b2f3a; color: #f0f0f0; border: 1px solid #555; border-radius: 6px; padding: 6px; }
            QTableWidget { background: #2b2f3a; color: #f0f0f0; gridline-color: #555; }
            QHeaderView::section { background: #3a3f4d; color: #eaeaea; padding: 6px; border: 0; }
            QGroupBox { border: 1px solid #444; border-radius: 8px; margin-top: 18px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            """
        )

# -----------------------------
# Entry point
# -----------------------------

def main():
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
