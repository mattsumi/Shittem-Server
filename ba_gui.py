#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets


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


class FuncWorker(QtCore.QThread):
    """
    Minimal QThread wrapper to run a callable off the GUI thread.
    """
    result = QtCore.Signal(object)
    error = QtCore.Signal(str)

    def __init__(self, func: t.Callable, *args, parent: QtCore.QObject | None = None, **kwargs):
        super().__init__(parent)
        self._func = func
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            res = self._func(*self._args, **self._kwargs)
            self.result.emit(res)
        except Exception as e:
            self.error.emit(str(e))


@dataclass
class AdminConfig:
    private_base: str = "http://127.0.0.1:7000"
    control_base: str = "http://127.0.0.1:9080"

class AdminClient:
    def __init__(self, cfg: AdminConfig):
        self.cfg = cfg
        self.http_private = Http(cfg.private_base)
        self.http_control = Http(cfg.control_base)

    def flip(self) -> str:
        try:
            return self.http_control.get_json("/_proxy/flip") or "OK"
        except HttpError as e:
            return str(e)

    def unflip(self) -> str:
        try:
            return self.http_control.get_json("/_proxy/unflip") or "OK"
        except HttpError as e:
            return str(e)

    def send_mail(self, account_id: int, subject: str, body: str,
                  attachments: list[dict[str, t.Any]] | None = None) -> t.Any:
        payload = {
            "accountId": account_id,
            "subject": subject,
            "body": body,
            "attachments": attachments or [],
        }
        return self.http_private.post_json("/admin/mail", payload)
    
    def queue_mail(self, mail, persistent=False):
        # mail: dict matching QueuedMail DTO; types are numeric (2/4), ids/amounts are ints
        body = {"mail": mail, "persistent": bool(persistent)}
        return self.http.post_json(self.base_url + "/admin/mail/queue", body)

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

    def list_types(self) -> t.Any:
        """
        Probe for catalog types. Returns whatever the server provides (list/dict).
        Raise HttpError if all HTTP options fail (model may attempt local file).
        """
        errors: list[str] = []
        for path in ("/admin/catalog/types", "/admin/catalog", "/admin/items/types"):
            try:
                return self.http_private.get_json(path)
            except Exception as e:
                errors.append(str(e))
        raise HttpError("All type routes failed: " + " | ".join(errors))

    def list_entities(self, type_name: str) -> t.Any:
        """
        Probe for entities of a given type. Returns server-provided payload (list/dict).
        Raises HttpError if all HTTP options fail (model may attempt local file).
        """
        tname = type_name
        errors: list[str] = []
        for path in (f"/admin/catalog/{tname}", f"/admin/catalog?type={parse.quote(tname)}",
                     f"/admin/items?type={parse.quote(tname)}"):
            try:
                return self.http_private.get_json(path)
            except Exception as e:
                errors.append(str(e))
        raise HttpError(f"All entity routes for '{tname}' failed: " + " | ".join(errors))

    def set_gacha_override(self, account_id: int, ids: list[int]) -> t.Any:
        """
        Attempt to set upcoming pull override. Tries likely endpoints and key names.
        """
        body_variants = [
            {"accountId": account_id, "unitIds": ids},
            {"accountId": account_id, "characterIds": ids},
            {"accountId": account_id, "studentIds": ids},
        ]
        paths = ["/admin/gacha/override", "/admin/gacha/set", "/admin/override/gacha"]
        errors: list[str] = []
        for p in paths:
            for payload in body_variants:
                try:
                    return self.http_private.post_json(p, payload)
                except HttpError as e:
                    # 404/501: try next path; other errors also bubble to next
                    errors.append(str(e))
                    continue
                except Exception as e:
                    errors.append(str(e))
                    continue
        raise HttpError("All gacha override attempts failed: " + " | ".join(errors))

    def clear_gacha_override(self, account_id: int) -> t.Any:
        """
        Attempt to clear override. Tries likely endpoints.
        """
        payload = {"accountId": account_id}
        paths = ["/admin/gacha/clear", "/admin/gacha/override/clear", "/admin/override/gacha/clear"]
        errors: list[str] = []
        for p in paths:
            try:
                return self.http_private.post_json(p, payload)
            except Exception as e:
                errors.append(str(e))
        raise HttpError("All gacha clear attempts failed: " + " | ".join(errors))


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
            return " ".join([f'"{path}"', *[shlex.quote(a) for a in args]])
        if lower.endswith((".exe", ".com")):
            return [path, *args]
        py = sys.executable
        return " ".join([f'"{py}"', "-m", "mitmproxy.tools.main", "mitmdump", *[shlex.quote(a) for a in args]])
    return [path, *args]


def _is_valid_mitmdump_text(text: str) -> bool:
    """
    Treat bare command names as valid when resolvable via PATH,
    otherwise require an existing file path.
    """
    if not text:
        return False
    p = Path(text)
    if p.is_absolute() or any((sep and sep in text) for sep in (os.sep, os.altsep)):
        return p.is_file()
    return shutil.which(text) is not None


def detect_addon_path() -> str | None:
    try:
        repo_candidate = Path(__file__).resolve().parents[1] / "mitm" / "blue_archive_addon.py"
        if repo_candidate.is_file():
            return str(repo_candidate)
    except Exception:
        pass
    cwd_candidate = Path.cwd() / "mitm" / "blue_archive_addon.py"
    if cwd_candidate.is_file():
        return str(cwd_candidate)
    return None


def detect_mitmdump_path() -> str | None:
    windows = os.name == "nt"
    exe_name = "mitmdump.exe" if windows else "mitmdump"

    # 1) PATH
    p = shutil.which("mitmdump")
    if p:
        return p
    if windows:
        p = shutil.which("mitmdump.exe")
        if p:
            return p

    scripts_dir = "Scripts" if windows else "bin"
    candidates: list[Path] = []

    # 2) Near current interpreter
    try:
        candidates.append(Path(sys.executable).with_name(scripts_dir) / exe_name)
    except Exception:
        pass
    try:
        candidates.append(Path(sys.base_prefix) / scripts_dir / exe_name)
    except Exception:
        pass

    # 3) PYTHONHOME
    pyhome = os.environ.get("PYTHONHOME")
    if pyhome:
        candidates.append(Path(pyhome) / scripts_dir / exe_name)

    # 4) Windows user installs (only immediate Python3* folders)
    if windows:
        user = os.environ.get("USERPROFILE", "")
        if user:
            for base in [
                Path(user) / "AppData" / "Local" / "Programs" / "Python",
                Path(user) / "AppData" / "Roaming" / "Python",
            ]:
                try:
                    for d in base.glob("Python3*"):
                        candidates.append(d / "Scripts" / "mitmdump.exe")
                except Exception:
                    pass

    for c in candidates:
        try:
            if c.is_file():
                return str(c)
        except Exception:
            continue
    return None

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
            shell=isinstance(self.cmd, str),
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


class CatalogModel(QtCore.QObject):
    def __init__(self, admin: AdminClient, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        self._admin = admin
        self._types: list[str] | None = None
        self._entities: dict[str, list[dict]] = {}
        self._lock = threading.RLock()
        self._local_catalog = (Path(__file__).parent / "game_catalog.json")

    def invalidate_type(self, type_name: str):
        with self._lock:
            self._entities.pop(type_name, None)

    def invalidate_all(self):
        with self._lock:
            self._types = None
            self._entities.clear()

    def fetch_types(self, parent: QtCore.QObject, on_done: t.Callable[[list[str]], None], on_error: t.Callable[[str], None]):
        worker = FuncWorker(self._load_types, parent=parent)
        worker.result.connect(lambda data: on_done(t.cast(list[str], data)))
        worker.error.connect(on_error)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def fetch_entities(self, type_name: str, parent: QtCore.QObject, on_done: t.Callable[[list[dict]], None], on_error: t.Callable[[str], None]):
        worker = FuncWorker(self._load_entities, type_name, parent=parent)
        worker.result.connect(lambda data: on_done(t.cast(list[dict], data)))
        worker.error.connect(on_error)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _load_types(self) -> list[str]:
        with self._lock:
            if self._types is not None:
                return list(self._types)
        try:
            raw = self._admin.list_types()
            types = self._normalize_types(raw)
            if types:
                print(f"[CATALOG] types loaded: {types}")
                with self._lock:
                    self._types = types
                return list(types)
        except Exception as e:
            print(f"[CATALOG] types remote load failed: {e}")
            pass
        print(f"[CATALOG] no types available from backend.")
        with self._lock:
            self._types = []
        return []

    def _load_entities(self, type_name: str) -> list[dict]:
        with self._lock:
            cached = self._entities.get(type_name)
            if cached is not None:
                return list(cached)
        try:
            raw = self._admin.list_entities(type_name)
            entities = self._normalize_entities(raw, type_name)
            print(f"[CATALOG] loaded {len(entities)} entities for type {type_name}")
            with self._lock:
                self._entities[type_name] = entities
            return list(entities)
        except Exception as e:
            print(f"[CATALOG] entity remote load failed for {type_name}: {e}")
            pass
        print(f"[CATALOG] no entities found for type {type_name}; caching empty list")
        with self._lock:
            self._entities[type_name] = []
        return []

    @staticmethod
    def _normalize_types(raw: t.Any) -> list[str]:
        # list[str]
        if isinstance(raw, list):
            out: list[str] = []
            for x in raw:
                if isinstance(x, str):
                    out.append(x.strip())
                elif isinstance(x, dict):
                    for k in ("type", "Type", "name", "Name"):
                        if k in x and isinstance(x[k], str):
                            out.append(x[k].strip())
            out = [t for t in out if t]
            return sorted(list(dict.fromkeys(out)))
        # dict => keys as types
        if isinstance(raw, dict):
            keys = [str(k) for k in raw.keys()]
            return sorted(list(dict.fromkeys(keys)))
        return []

    @staticmethod
    def _normalize_entities(raw: t.Any, type_name: str) -> list[dict]:
        def norm_entry(d: dict) -> dict | None:
            # Find an ID
            id_keys = ("id", "Id", "ID", "entityId", "itemId", "unitId", "characterId", "entity_id", "unit_id", "character_id")
            name_keys = ("name", "Name", "canonicalName", "displayName", "dev_name", "devName", "title")
            _id: int | None = None
            if isinstance(d, dict):
                for k in id_keys:
                    if k in d:
                        try:
                            _id = int(d[k])
                            break
                        except Exception:
                            continue
                if _id is None and len(d) == 1:
                    # maybe {"123":"Foo"}
                    try:
                        only_key = next(iter(d.keys()))
                        _id = int(only_key)
                    except Exception:
                        pass
                _name = None
                for k in name_keys:
                    if k in d and isinstance(d[k], (str, int)):
                        _name = str(d[k])
                        break
                if _id is None:
                    return None
                # safe label if missing/empty
                if _name is None or not str(_name).strip():
                    _name = f"(Unnamed) [{_id}]"
                return {"id": int(_id), "name": str(_name)}
            return None

        out: list[dict] = []
        if isinstance(raw, list):
            for row in raw:
                if isinstance(row, dict):
                    ne = norm_entry(row)
                    if ne:
                        out.append(ne)
                elif isinstance(row, (str, int)):
                    # bare IDs
                    try:
                        iid = int(row)
                        out.append({"id": iid, "name": str(iid)})
                    except Exception:
                        pass
        elif isinstance(raw, dict):
            for k, v in raw.items():
                try:
                    iid = int(k)
                    name = v if isinstance(v, str) else str(iid)
                    out.append({"id": iid, "name": name})
                except Exception:
                    # or dict entries
                    if isinstance(v, dict):
                        ne = norm_entry(v)
                        if ne:
                            out.append(ne)
        # dedupe, stable
        dedup: dict[int, dict] = {}
        for e in out:
            dedup[e["id"]] = e
        out = list(dedup.values())
        out.sort(key=lambda x: (x["name"].lower(), x["id"]))
        return out


class MailTab(QtWidgets.QWidget):
    def __init__(self, admin: AdminClient, catalog: CatalogModel, parent=None):
        super().__init__(parent)
        self.admin = admin
        self.catalog = catalog
        self._entities_current: list[dict] = []
        self._entities_filtered: list[dict] = []

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

        # Picker row
        picker = QtWidgets.QHBoxLayout()
        self.type_combo = QtWidgets.QComboBox(); self.type_combo.setEnabled(False)
        self.type_refresh = QtWidgets.QToolButton(); self.type_refresh.setText("↻")
        self.filter_edit = QtWidgets.QLineEdit(); self.filter_edit.setPlaceholderText("Filter…")
        self.entity_combo = QtWidgets.QComboBox(); self.entity_combo.setEnabled(False)
        self.qty_spin = QtWidgets.QSpinBox(); self.qty_spin.setRange(1, 10_000); self.qty_spin.setValue(1)
        self.note_edit = QtWidgets.QLineEdit(); self.note_edit.setPlaceholderText("Note (optional)")
        self.picker_add = PrettyButton("Add")

        picker.addWidget(QtWidgets.QLabel("Add via picker:"))
        picker.addWidget(self.type_combo, 1)
        picker.addWidget(self.type_refresh)
        picker.addWidget(self.filter_edit, 1)
        picker.addWidget(self.entity_combo, 2)
        picker.addWidget(QtWidgets.QLabel("Qty:"))
        picker.addWidget(self.qty_spin)
        picker.addWidget(self.note_edit, 1)
        picker.addWidget(self.picker_add)

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

        # inline status
        self.status_label = QtWidgets.QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.hide()

        add.clicked.connect(self._add_row)
        rem.clicked.connect(self._remove_selected)
        send.clicked.connect(self._send)

        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        self.type_refresh.clicked.connect(self._refresh_current_type)
        self.filter_edit.textChanged.connect(self._apply_entity_filter)
        self.picker_add.clicked.connect(self._picker_add_clicked)

        main.addLayout(grid)
        main.addLayout(picker)
        main.addWidget(self.table, 1)
        main.addWidget(self.status_label)
        main.addLayout(btns)

        # Load types async and restore settings
        QtCore.QTimer.singleShot(0, self._init_types_and_settings)

    def _settings(self) -> QtCore.QSettings:
        return QtCore.QSettings("ShittimServer", "AdminGUI")

    def _init_types_and_settings(self):
        self._set_picker_busy(True)
        def on_done(types: list[str]):
            self.type_combo.clear()
            # Only allow item-like types for attachments; exclude characters/units/students
            allowed = [t for t in types if not any(w in t.lower() for w in ("character", "characters", "unit", "units", "student", "students"))]
            
            preferred_order = ["Currency", "Item", "Gear", "Weapon", "GachaGroup"]
            
            ordered_types = sorted(allowed, key=lambda t: (preferred_order.index(t) if t in preferred_order else len(preferred_order), t))

            if not ordered_types and types:
                # Fallback if preferred types are not present, but still exclude characters
                ordered_types = sorted(allowed)

            if not ordered_types:
                self._show_status("No mail-eligible types available from backend.")
                self.type_combo.setEnabled(False)
                self.entity_combo.setEnabled(False)
                self.picker_add.setEnabled(False)
                self._set_picker_busy(False)
                return
            for tname in ordered_types:
                self.type_combo.addItem(tname)
            self.type_combo.setEnabled(True)
            # restore last values
            s = self._settings()
            filt = s.value("mail/filter", "", str)
            if isinstance(filt, str):
                self.filter_edit.setText(filt)
            last_type = s.value("mail/last_type", "", str)
            if last_type:
                idx = self.type_combo.findText(last_type)
                if idx >= 0:
                    self.type_combo.setCurrentIndex(idx)
            if self.type_combo.currentIndex() < 0 and self.type_combo.count() > 0:
                self.type_combo.setCurrentIndex(0)
            # trigger entity load
            self._on_type_changed()
            self._set_picker_busy(False)
            self._show_status("")
        def on_err(msg: str):
            self._show_status(f"Could not load types from backend. {msg}")
            self.type_combo.clear()
            self.type_combo.setEnabled(False)
            self.entity_combo.setEnabled(False)
            self.picker_add.setEnabled(False)
            self._set_picker_busy(False)
        self.catalog.fetch_types(self, on_done, on_err)

    def _set_picker_busy(self, busy: bool):
        for w in (self.type_combo, self.type_refresh, self.filter_edit, self.entity_combo, self.qty_spin, self.note_edit, self.picker_add):
            w.setEnabled(not busy)

    def _show_status(self, msg: str):
        if msg:
            self.status_label.setText(msg)
            self.status_label.show()
        else:
            self.status_label.hide()
            self.status_label.setText("")

    def _apply_entity_filter(self):
        s = self._settings()
        s.setValue("mail/filter", self.filter_edit.text())
        text = self.filter_edit.text().strip().lower()
        if not text:
            # reset to all
            self._populate_entity_combo(self._entities_current)
            return
        out: list[dict] = []
        for e in self._entities_current:
            if text in e["name"].lower() or text in str(e["id"]).lower():
                out.append(e)
        self._entities_filtered = out
        self._populate_entity_combo(out)

    def _populate_entity_combo(self, items: list[dict]):
        # keep current selection if possible
        current_id = self._current_entity_id()
        self.entity_combo.blockSignals(True)
        self.entity_combo.clear()
        for e in items:
            self.entity_combo.addItem(f"{e['name']} ({e['id']})", e["id"])
        self.entity_combo.blockSignals(False)
        # restore by id
        if current_id is not None:
            for i in range(self.entity_combo.count()):
                if self.entity_combo.itemData(i) == current_id:
                    self.entity_combo.setCurrentIndex(i)
                    break

    def _current_entity_id(self) -> int | None:
        idx = self.entity_combo.currentIndex()
        if idx < 0:
            return None
        try:
            return int(self.entity_combo.itemData(idx))
        except Exception:
            return None

    def _on_type_changed(self):
        # persist last type
        s = self._settings()
        s.setValue("mail/last_type", self.type_combo.currentText())
        # load entities async
        tname = self.type_combo.currentText().strip()
        if not tname:
            return
        # Disallow character-like types for attachments
        lname = tname.lower()
        if any(w in lname for w in ("character","characters","unit","units","student","students")):
            self._entities_current = []
            self._populate_entity_combo([])
            self.entity_combo.setEnabled(False)
            self.picker_add.setEnabled(False)
            self._show_status("Attachments accept only item-like types.")
            return
        print(f"[MAIL] loading entities for type {tname}")
        self.entity_combo.clear()
        self.entity_combo.addItem("Loading…")
        self.entity_combo.setEnabled(False)
        self._show_status("")
        self._set_picker_busy(True)
        def on_done(items: list[dict]):
            print(f"[MAIL] entities ready for type {tname}: {len(items)}")
            self._entities_current = list(items)
            self._apply_entity_filter()
            self.entity_combo.setEnabled(True)
            self.picker_add.setEnabled(True)
            self._set_picker_busy(False)
            # restore last entity id
            last_id = s.value("mail/last_entity_id", "", str)
            if last_id:
                try:
                    lid = int(last_id)
                    for i in range(self.entity_combo.count()):
                        if self.entity_combo.itemData(i) == lid:
                            self.entity_combo.setCurrentIndex(i)
                            break
                except Exception:
                    pass
            self._show_status("")
        def on_err(msg: str):
            print(f"[MAIL] entities load failed for {tname}: {msg}")
            self._entities_current = self.catalog._load_entities(tname)
            if not self._entities_current:
                self.entity_combo.clear()
                self.entity_combo.setEnabled(False)
                self.picker_add.setEnabled(False)
                self._show_status(f"No entities found for {tname}.")
            else:
                self._apply_entity_filter()
                self.entity_combo.setEnabled(True)
                self.picker_add.setEnabled(True)
                self._show_status(f"Failed to fetch from server; using fallback for {tname}.")
            self._set_picker_busy(False)
        self.catalog.fetch_entities(tname, self, on_done, on_err)

    def _refresh_current_type(self):
        tname = self.type_combo.currentText().strip()
        if not tname:
            return
        self.catalog.invalidate_type(tname)
        self._on_type_changed()

    def _picker_add_clicked(self):
        ent_id = self._current_entity_id()
        if ent_id is None:
            QtWidgets.QMessageBox.information(self, "Picker", "Choose an entity first.")
            return
        qty = self.qty_spin.value()
        note = self.note_edit.text().strip()
        # persist last entity id
        s = self._settings()
        s.setValue("mail/last_entity_id", str(ent_id))
        # append a row
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(ent_id)))
        self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(qty)))
        self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(note))

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
        attachments: list[dict] = []
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


class GachaTab(QtWidgets.QWidget):
    def __init__(self, admin: AdminClient, catalog: CatalogModel, parent=None):
        super().__init__(parent)
        self.admin = admin
        self.catalog = catalog
        self._char_type: str | None = None
        self._entities: list[dict] = []

        v = QtWidgets.QVBoxLayout(self)

        # Account line
        self.account = LabeledLine("Account ID:", "3218642")
        v.addWidget(self.account)

        # Mode selection
        mode_box = QtWidgets.QGroupBox("Override Mode")
        hb = QtWidgets.QHBoxLayout(mode_box)
        self.one_pull = QtWidgets.QRadioButton("Next 1 pull")
        self.ten_pull = QtWidgets.QRadioButton("Next 10 pull")
        self.ten_pull.setChecked(True)
        group = QtWidgets.QButtonGroup(self)
        group.addButton(self.one_pull)
        group.addButton(self.ten_pull)
        self.one_pull.toggled.connect(self._update_mode_controls)
        self.ten_pull.toggled.connect(self._update_mode_controls)
        hb.addWidget(self.one_pull)
        hb.addWidget(self.ten_pull)
        hb.addStretch(1)
        v.addWidget(mode_box)

        # Picker (type locked)
        picker = QtWidgets.QHBoxLayout()
        self.type_lbl = QtWidgets.QLabel("Type:")
        self.type_locked = QtWidgets.QLineEdit()
        self.type_locked.setReadOnly(True)
        self.filter_edit = QtWidgets.QLineEdit(); self.filter_edit.setPlaceholderText("Filter…")
        self.entity_combo = QtWidgets.QComboBox(); self.entity_combo.setEnabled(False)
        self.add_btn = PrettyButton("Add")
        self.fill_btn = PrettyButton("Fill x10")
        picker.addWidget(self.type_lbl)
        picker.addWidget(self.type_locked, 1)
        picker.addWidget(self.filter_edit, 1)
        picker.addWidget(self.entity_combo, 2)
        picker.addWidget(self.add_btn)
        picker.addWidget(self.fill_btn)
        v.addLayout(picker)

        # Preview table
        self.table = QtWidgets.QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["UnitId", "Name"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        v.addWidget(self.table, 1)

        # Remove button
        row_btns = QtWidgets.QHBoxLayout()
        self.remove_btn = PrettyButton("Remove Selected")
        row_btns.addWidget(self.remove_btn)
        row_btns.addStretch(1)
        v.addLayout(row_btns)

        # Action buttons
        bottom = QtWidgets.QHBoxLayout()
        self.set_btn = PrettyButton("Set Override")
        self.clear_btn = PrettyButton("Clear Override")
        bottom.addStretch(1)
        bottom.addWidget(self.set_btn)
        bottom.addWidget(self.clear_btn)
        v.addLayout(bottom)

        # Inline status/notice
        self.status_label = QtWidgets.QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        v.addWidget(self.status_label)

        # Wire events
        self.filter_edit.textChanged.connect(self._apply_filter)
        self.add_btn.clicked.connect(self._add_selected)
        self.fill_btn.clicked.connect(self._fill_x10)
        self.remove_btn.clicked.connect(self._remove_selected)
        self.set_btn.clicked.connect(self._set_override)
        self.clear_btn.clicked.connect(self._clear_override)

        # Initialize mode control state
        self._update_mode_controls()
        # Load catalog and restore settings
        QtCore.QTimer.singleShot(0, self._init_types_and_entities)

    def _settings(self) -> QtCore.QSettings:
        return QtCore.QSettings("ShittimServer", "AdminGUI")

    def _update_mode_controls(self):
        ten = self.ten_pull.isChecked()
        # enable add/fill only for 10-pull mode and when picker enabled
        can_pick = self.entity_combo.isEnabled()
        self.add_btn.setEnabled(ten and can_pick)
        self.fill_btn.setEnabled(ten and can_pick)

    def _set_picker_enabled(self, en: bool):
        for w in (self.filter_edit, self.entity_combo, self.add_btn, self.fill_btn):
            w.setEnabled(en)

    def _init_types_and_entities(self):
        # pick a character-like type
        def on_types(types: list[str]):
            s = self._settings()
            pref_saved = s.value("gacha/last_type", "", str)
            picked = None
            if pref_saved and pref_saved in types:
                picked = pref_saved
            else:
                # Choose 'Character' or 'Unit' (or variants)
                prefer = ["Character", "Characters", "Unit", "Units", "Student", "Students"]
                for p in prefer:
                    for tname in types:
                        if tname.lower() == p.lower():
                            picked = tname
                            break
                    if picked:
                        break
                if not picked:
                    picked = types[0] if types else "Character"
            self._char_type = picked
            self.type_locked.setText(picked)
            s.setValue("gacha/last_type", picked)
            # load entities
            self._set_picker_enabled(False)
            self.entity_combo.clear()
            self.entity_combo.addItem("Loading…")
            self.entity_combo.setEnabled(False)
            self.catalog.fetch_entities(picked, self, self._on_entities_loaded, self._on_entities_error)
        def on_err(msg: str):
            self._show_status(f"Could not load character types from backend. {msg}")
            self._set_controls_enabled(False)
            self._set_picker_enabled(False)
        self._set_picker_enabled(False)
        self.catalog.fetch_types(self, on_types, on_err)

    def _on_entities_loaded(self, entities: list[dict]):
        self._entities = entities
        print(f"[GACHA] entities ready for type {self._char_type}: {len(entities)}")
        self._apply_filter()
        self._set_picker_enabled(True)
        self._update_mode_controls()
        # restore last selected entity
        s = self._settings()
        last_id = s.value("gacha/last_entity_id", "", str)
        if last_id:
            try:
                lid = int(last_id)
                for i in range(self.entity_combo.count()):
                    if self.entity_combo.itemData(i) == lid:
                        self.entity_combo.setCurrentIndex(i)
                        break
            except Exception:
                pass
        self._show_status("")

    def _on_entities_error(self, msg: str):
        self._entities = self.catalog._load_entities(self._char_type or "Character")
        if not self._entities:
            self._set_controls_enabled(False)
            self._set_picker_enabled(False)
            self._show_status("Could not load character catalog from server.")
            return
        self._apply_filter()
        self._set_picker_enabled(True)
        self._show_status(f"Gacha entity list unavailable; using fallback if any. {msg}")

    def _apply_filter(self):
        s = self._settings()
        s.setValue("gacha/filter", self.filter_edit.text())
        text = self.filter_edit.text().strip().lower()
        self.entity_combo.blockSignals(True)
        self.entity_combo.clear()
        items = self._entities
        if text:
            items = [e for e in items if text in e["name"].lower() or text in str(e["id"]).lower()]
        for e in items:
            self.entity_combo.addItem(f"{e['name']} ({e['id']})", e["id"])
        self.entity_combo.blockSignals(False)

    def _selected_id(self) -> int | None:
        idx = self.entity_combo.currentIndex()
        if idx < 0:
            return None
        try:
            return int(self.entity_combo.itemData(idx))
        except Exception:
            return None

    def _add_selected(self):
        ent = self._selected_id()
        if ent is None:
            QtWidgets.QMessageBox.information(self, "Gacha", "Select a character first.")
            return
        # persist last entity
        s = self._settings()
        s.setValue("gacha/last_entity_id", str(ent))
        # add row if capacity allows
        if self.ten_pull.isChecked() and self.table.rowCount() >= 10:
            QtWidgets.QMessageBox.information(self, "Gacha", "You already have 10 rows.")
            return
        self._append_row(ent, self._name_for(ent))

    def _fill_x10(self):
        ent = self._selected_id()
        if ent is None:
            QtWidgets.QMessageBox.information(self, "Gacha", "Select a character to fill.")
            return
        self.table.setRowCount(0)
        for _ in range(10):
            self._append_row(ent, self._name_for(ent))

    def _name_for(self, ent_id: int) -> str:
        for e in self._entities:
            if e["id"] == ent_id:
                return e["name"]
        return str(ent_id)

    def _append_row(self, ent_id: int, name: str):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(ent_id)))
        self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(name))

    def _remove_selected(self):
        for idx in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(idx)

    def _set_controls_enabled(self, en: bool):
        for w in (self.account.edit, self.one_pull, self.ten_pull, self.filter_edit, self.entity_combo,
                  self.add_btn, self.fill_btn, self.remove_btn, self.set_btn, self.clear_btn):
            w.setEnabled(en)

    def _show_status(self, msg: str):
        if msg:
            self.status_label.setText(msg)
            self.status_label.show()
        else:
            self.status_label.hide()
            self.status_label.setText("")

    def _collect_ids(self) -> list[int]:
        ids: list[int] = []
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item and item.text().strip():
                try:
                    ids.append(int(item.text().strip()))
                except Exception:
                    pass
        return ids

    def _set_override(self):
        try:
            account_id = int(self.account.text())
        except Exception:
            QtWidgets.QMessageBox.warning(self, "Gacha", "Account ID must be an integer")
            return
        expected = 1 if self.one_pull.isChecked() else 10
        ids = self._collect_ids()
        if self.one_pull.isChecked():
            # allow auto from picker if table empty
            if not ids:
                sel = self._selected_id()
                if sel is None:
                    QtWidgets.QMessageBox.information(self, "Gacha", "Pick a character or add one row.")
                    return
                ids = [sel]
        if len(ids) != expected:
            QtWidgets.QMessageBox.information(self, "Gacha", f"Expected exactly {expected} row(s); you have {len(ids)}.")
            return

        self._set_controls_enabled(False)
        def do_set():
            return self.admin.set_gacha_override(account_id, ids)
        worker = FuncWorker(do_set, parent=self)
        def ok(res: object):
            self._set_controls_enabled(True)
            self._show_status("")
            QtWidgets.QMessageBox.information(self, "Gacha", json.dumps(res, indent=2))
        def err(msg: str):
            self._set_controls_enabled(True)
            self._show_status("")
            if "-> 404" in msg or "-> 501" in msg:
                self._set_controls_enabled(False)
                self._show_status("Backend does not advertise gacha override endpoints. Controls disabled.")
            else:
                QtWidgets.QMessageBox.critical(self, "Gacha", msg)
        worker.result.connect(ok)
        worker.error.connect(err)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _clear_override(self):
        try:
            account_id = int(self.account.text())
        except Exception:
            QtWidgets.QMessageBox.warning(self, "Gacha", "Account ID must be an integer")
            return
        self._set_controls_enabled(False)
        worker = FuncWorker(lambda: self.admin.clear_gacha_override(account_id), parent=self)
        def ok(res: object):
            self._set_controls_enabled(True)
            self._show_status("")
            QtWidgets.QMessageBox.information(self, "Gacha", json.dumps(res, indent=2))
        def err(msg: str):
            self._set_controls_enabled(True)
            self._show_status("")
            if "-> 404" in msg or "-> 501" in msg:
                self._set_controls_enabled(False)
                self._show_status("Backend does not advertise gacha override endpoints. Controls disabled.")
            else:
                QtWidgets.QMessageBox.critical(self, "Gacha", msg)
        worker.result.connect(ok)
        worker.error.connect(err)
        worker.finished.connect(worker.deleteLater)
        worker.start()


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

        # Load persisted settings and wire change handlers
        QtCore.QTimer.singleShot(0, self._load_and_wire_settings)

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

    def _settings(self) -> QtCore.QSettings:
        return QtCore.QSettings("ShittimServer", "AdminGUI")

    def _load_and_wire_settings(self):
        s = self._settings()
        # load
        self.private_url.setText(s.value("server/private_base", self.private_url.text(), str))
        self.control_url.setText(s.value("server/control_base", self.control_url.text(), str))
        self.mitmdump.setText(s.value("server/mitmdump", self.mitmdump.text(), str))
        self.addon.setText(s.value("server/addon", self.addon.text(), str))
        self.listen_host.setText(s.value("server/listen_host", self.listen_host.text(), str))
        self.listen_port.setText(s.value("server/listen_port", self.listen_port.text(), str))
        self.dotnet_dir.setText(s.value("server/dotnet_dir", self.dotnet_dir.text(), str))

        # auto-detect only when empty or invalid, before wiring signals
        cur_mitmdump = self.mitmdump.text().strip()
        if (not cur_mitmdump) or (not _is_valid_mitmdump_text(cur_mitmdump)):
            detected = detect_mitmdump_path()
            if detected:
                self.mitmdump.setText(detected)
                s.setValue("server/mitmdump", detected)
                print(f"[AUTO] mitmdump detected at: {detected}")
            else:
                print("[AUTO] mitmdump not found")

        cur_addon = self.addon.text().strip()
        addon_ok = bool(cur_addon) and Path(cur_addon).is_file()
        if not addon_ok:
            detected_addon = detect_addon_path()
            if detected_addon:
                self.addon.setText(detected_addon)
                s.setValue("server/addon", detected_addon)
                print(f"[AUTO] addon detected at: {detected_addon}")
            else:
                print("[AUTO] addon not found")

        self.private_url.textChanged.connect(lambda v: s.setValue("server/private_base", v))
        self.control_url.textChanged.connect(lambda v: s.setValue("server/control_base", v))
        self.mitmdump.textChanged.connect(lambda v: s.setValue("server/mitmdump", v))
        self.addon.textChanged.connect(lambda v: s.setValue("server/addon", v))
        self.listen_host.textChanged.connect(lambda v: s.setValue("server/listen_host", v))
        self.listen_port.textChanged.connect(lambda v: s.setValue("server/listen_port", v))
        self.dotnet_dir.textChanged.connect(lambda v: s.setValue("server/dotnet_dir", v))


class LogsTab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        v = QtWidgets.QVBoxLayout(self)
        self.view = QtWidgets.QPlainTextEdit(); self.view.setReadOnly(True)
        self.view.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))
        v.addWidget(self.view)

    def append(self, line: str):
        self.view.appendPlainText(line)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Blue Archive – Admin Console")
        self.resize(1080, 720)
        self.setWindowIcon(QtGui.QIcon.fromTheme("applications-games"))

        # Load settings first to seed config
        settings = QtCore.QSettings("ShittimServer", "AdminGUI")
        cfg = AdminConfig()
        cfg.private_base = settings.value("server/private_base", cfg.private_base, str)
        cfg.control_base = settings.value("server/control_base", cfg.control_base, str)

        # Global client + catalog model
        self.admin = AdminClient(cfg)
        self.catalog = CatalogModel(self.admin, parent=self)

        # Tabs
        tabs = QtWidgets.QTabWidget()
        tabs.setDocumentMode(True)
        tabs.setTabPosition(QtWidgets.QTabWidget.North)
        tabs.setMovable(True)
        self.mail_tab = MailTab(self.admin, self.catalog)
        self.notice_tab = NoticeTab(self.admin)
        self.account_tab = AccountTab(self.admin)
        self.gacha_tab = GachaTab(self.admin, self.catalog)
        self.server_tab = ServerTab(self.admin)
        self.logs_tab = LogsTab()

        tabs.addTab(self.mail_tab, "📬 Mail")
        tabs.addTab(self.notice_tab, "📣 Notices")
        tabs.addTab(self.account_tab, "👤 Account")
        tabs.addTab(self.gacha_tab, "🎲 Gacha")
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


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
