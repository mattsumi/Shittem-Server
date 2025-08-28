#!/usr/bin/env python3
import json
import logging
import os
import random
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from mitmproxy import ctx, http

# --- Config ------------------------------------------------------------------

TARGET_DOMAINS: List[str] = [
    "nxm-eu-bagl.nexon.com",
    "public.api.nexon.com",
    "signin.nexon.com",
    "config.na.nexon.com",
    "psm-log.ngs.nexon.com",
    "x-config.ngs.nexon.com",
    "x-csauth.ngs.nexon.com",
    "x-init.ngs.nexon.com",
    "x-update.ngs.nexon.com",
    "accio.ngsm.nexon.com",
    "bluearchive.nexon.com",
    "toy.log.nexon.io",
    "gtable.inface.nexon.com",
    "ba.dn.nexoncdn.co.kr",
    "jarvis.dn.nexoncdn.co.kr",
    "d2vaidpni345rp.cloudfront.net",
]

# Admin/private API location (local)
PRIVATE_HOST: str = os.getenv("BA_PRIVATE_HOST", "127.0.0.1")
PRIVATE_PORT: int = int(os.getenv("BA_PRIVATE_PORT", "7000"))
PRIVATE_SCHEME: str = os.getenv("BA_PRIVATE_SCHEME", "http")
PRIVATE_SERVER: Tuple[str, int] = (PRIVATE_HOST, PRIVATE_PORT)
ADMIN_BASE = f"{PRIVATE_SCHEME}://{PRIVATE_HOST}:{PRIVATE_PORT}/admin/mail"

# Where SchaleDB json lives (ids → types)
DATA_DIR = Path(os.getenv("BA_DATA_DIR", "data")) / "en"
CURRENCY_PATH = DATA_DIR / "currency.json"
ITEMS_PATH = DATA_DIR / "items.json"
EQUIPMENT_PATH = DATA_DIR / "equipment.json"

# parcel key type values (minimal)
TYPE_CURRENCY = 2
TYPE_ITEM = 4
# If equipment needs a distinct type, add it here; defaulting to ITEM works for most attachments.

if "BA_TARGET_DOMAINS" in os.environ:
    TARGET_DOMAINS = [
        d.strip() for d in os.getenv("BA_TARGET_DOMAINS", "").split(",") if d.strip()
    ]

LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

# --- Tiny local HTTP helpers (no requests dependency) ------------------------

def _http_get_json(url: str, timeout: float = 2.0) -> Optional[Dict]:
    import urllib.request, urllib.error
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = r.read().decode("utf-8")
            return json.loads(data)
    except Exception as e:
        ctx.log.warn(f"[ADDON] GET {url} failed: {e}")
        return None

def _http_post_json(url: str, payload: Dict, timeout: float = 2.0) -> Optional[Dict]:
    import urllib.request, urllib.error
    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read().decode("utf-8")
            return json.loads(data) if data else {}
    except Exception as e:
        ctx.log.warn(f"[ADDON] POST {url} failed: {e}")
        return None

# --- Stats & logging ---------------------------------------------------------

class RequestStats:
    def __init__(self):
        self.requests_total = 0
        self.private_count = 0
        self.official_count = 0
        self.started_at = time.time()
        self._lock = threading.Lock()

    def increment_private(self):
        with self._lock:
            self.requests_total += 1
            self.private_count += 1

    def increment_official(self):
        with self._lock:
            self.requests_total += 1
            self.official_count += 1

    def get_stats(self) -> Dict:
        with self._lock:
            return {
                "requests_total": self.requests_total,
                "private_count": self.private_count,
                "official_count": self.official_count,
                "started_at": self.started_at,
            }

class JSONLLogger:
    def __init__(self):
        self.current_date = None
        self.current_file = None
        self._lock = threading.Lock()

    def _get_log_file(self):
        today = datetime.now().strftime("%Y%m%d")
        if today != self.current_date:
            if self.current_file:
                self.current_file.close()
            self.current_date = today
            path = LOGS_DIR / f"mitm_{today}.jsonl"
            self.current_file = open(path, "a", encoding="utf-8")
        return self.current_file

    def log_request(self, entry: Dict):
        with self._lock:
            try:
                f = self._get_log_file()
                f.write(json.dumps(entry) + "\n")
                f.flush()
            except Exception as e:
                ctx.log.error(f"Failed to write JSONL log: {e}")

class SharedState:
    def __init__(self):
        self.flipped: bool = False
        self.stats = RequestStats()
        self.logger = JSONLLogger()
        self._lock = threading.Lock()

state = SharedState()

# --- Control server (flip/unflip/status) -------------------------------------

class ControlHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/_proxy/flip":
            state.flipped = True
            self._send_json({"flipped": True})
            ctx.log.info("Traffic flipping ENABLED - API requests now route to private server")
            return

        if self.path == "/_proxy/unflip":
            state.flipped = False
            self._send_json({"flipped": False})
            ctx.log.info("Traffic flipping DISABLED - requests go to official servers (injection active)")
            return

        if self.path == "/_proxy/health":
            self._send_json({"status": "ok"})
            return

        if self.path == "/_proxy/status":
            stats = state.stats.get_stats()
            self._send_json({
                "flipped": state.flipped,
                "private_host": PRIVATE_HOST,
                "private_port": PRIVATE_PORT,
                "target_domains": TARGET_DOMAINS,
                "requests_total": stats["requests_total"],
                "private_count": stats["private_count"],
                "official_count": stats["official_count"],
                "started_at": stats["started_at"],
                "now": time.time(),
            })
            return

        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error": "Not Found"}')

    def _send_json(self, data: Dict) -> None:
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        pass

def start_control_server() -> None:
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 9080), ControlHandler)
        ctx.log.info("Control server listening on http://127.0.0.1:9080")
        server.serve_forever()
    except Exception as e:
        ctx.log.error(f"Control server failed to start: {e}")

# --- Addon -------------------------------------------------------------------

class BlueArchiveAddon:
    def __init__(self):
        self._control_thread_started = False
        self._kind_map = {}  # itemId -> parcel type (2 currency, 4 item)

    # ---------- helpers for SchaleDB kinds ----------
    def _load_ids(self, path: Path, kind: int):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # SchaleDB uses Id
            for row in data:
                iid = row.get("Id")
                if iid is not None:
                    self._kind_map[int(iid)] = kind
            ctx.log.info(f"[ADDON] loaded {len(data)} ids from {path.name} as kind={kind}")
        except FileNotFoundError:
            ctx.log.warn(f"[ADDON] {path} not found (ok if unused)")
        except Exception as e:
            ctx.log.warn(f"[ADDON] failed to read {path}: {e}")

    def _load_kind_map(self):
        self._load_ids(CURRENCY_PATH, TYPE_CURRENCY)
        self._load_ids(ITEMS_PATH, TYPE_ITEM)
        # Equipment will default to TYPE_ITEM unless you add a distinct type here.
        self._load_ids(EQUIPMENT_PATH, TYPE_ITEM)

    def load(self, loader) -> None:
        if not self._control_thread_started:
            th = threading.Thread(target=start_control_server, daemon=True, name="ControlServer")
            th.start()
            self._control_thread_started = True

        self._load_kind_map()
        ctx.log.info("Blue Archive MITM addon loaded")
        ctx.log.info(f"Target domains: {len(TARGET_DOMAINS)} configured")
        ctx.log.info(f"Private server: {PRIVATE_SCHEME}://{PRIVATE_HOST}:{PRIVATE_PORT}")
        ctx.log.info("Use http://127.0.0.1:9080/_proxy/unflip for OFFICIAL mode (injection ON).")

    # ---------- request path rewrite when flipped ----------
    def request(self, flow: http.HTTPFlow) -> None:
        if not state.flipped:
            return

        original_host = flow.request.pretty_host
        if not original_host:
            return

        host_no_port = original_host.split(":", 1)[0].lower()
        original_port = flow.request.port
        sni_host = getattr(flow.request, "sni", "") or ""

        should_redirect = False
        if original_port in (5000, 5100):
            is_ba_gateway = (
                any(host_no_port.endswith(d.lower()) for d in TARGET_DOMAINS)
                or any(sni_host.lower().endswith(d.lower()) for d in TARGET_DOMAINS)
                or (sni_host.startswith("nxm-") and sni_host.endswith("-bagl.nexon.com"))
                or (host_no_port.startswith("nxm-") and host_no_port.endswith("-bagl.nexon.com"))
            )
            should_redirect = is_ba_gateway

        if not should_redirect:
            return

        original_path = flow.request.path
        flow.request.scheme = PRIVATE_SCHEME
        flow.request.host = PRIVATE_SERVER[0]
        flow.request.port = PRIVATE_SERVER[1]
        flow.request.path = "/api/gateway"
        flow.request.headers["Host"] = f"{PRIVATE_SERVER[0]}:{PRIVATE_SERVER[1]}"
        flow.request.headers["X-Original-Host"] = original_host
        flow.request.headers["X-Original-Path"] = original_path
        flow.request.headers["X-Original-Port"] = str(original_port)
        new_target = f"{PRIVATE_SCHEME}://{PRIVATE_SERVER[0]}:{PRIVATE_SERVER[1]}/api/gateway"
        ctx.log.info(f"REDIRECT -> {new_target} (method: {flow.request.method})")

    # ---------- response injection when NOT flipped ----------
    def _looks_like_gateway(self, flow: http.HTTPFlow) -> bool:
        host = (flow.request.pretty_host or "").lower()
        return any(host.endswith(d.lower()) for d in TARGET_DOMAINS) and flow.request.path.endswith("/api/gateway")

    def _guess_account_id(self, packet: Dict) -> Optional[int]:
        mdb = packet.get("MailDBs") or []
        if mdb and isinstance(mdb, list):
            acct = mdb[0].get("AccountServerId")
            if isinstance(acct, int):
                return acct
        return None

    def _parcel_for(self, item_id: int, count: int) -> Dict:
        kind = self._kind_map.get(int(item_id), TYPE_ITEM)
        return {
            "Key": {"Type": kind, "Id": int(item_id)},
            "Amount": int(count),
            "Multiplier": {"rawValue": 10000},
            "Probability": {"rawValue": 10000},
        }

    def _maildb_from_queued(self, qmail: Dict, acct_id: Optional[int]) -> Dict:
        subject = qmail.get("Subject") or "Admin Mail"
        created_at = qmail.get("CreatedAt")
        send_dt = datetime.fromisoformat(created_at) if created_at else datetime.utcnow()
        expire_dt = send_dt + timedelta(days=7)

        parcels = []
        for att in qmail.get("Attachments", []):
            iid = att.get("ItemId")
            cnt = att.get("Count", 1)
            if iid is None:
                continue
            parcels.append(self._parcel_for(int(iid), int(cnt)))

        server_id = random.randint(10_000_000, 99_999_999)
        # Use UI constants like official does; safe defaults:
        sender_key = "UI_MAILBOX_POST_SENDER_ARONA"

        return {
            "ServerId": server_id,
            "AccountServerId": acct_id,
            "UniqueId": -1,
            "Sender": sender_key,
            "LocalizedSender": {"Kr": sender_key, "En": sender_key, "Th": sender_key, "Tw": sender_key},
            "Comment": subject,
            "LocalizedComment": {"Kr": subject, "En": subject, "Th": subject, "Tw": subject},
            "SendDate": send_dt.replace(microsecond=0).isoformat(),
            "ExpireDate": expire_dt.replace(microsecond=0).isoformat(),
            "ParcelInfos": parcels,
        }

    def _inject_mail(self, flow: http.HTTPFlow):
        # Only when NOT flipped and the host looks like official BA gateway
        if state.flipped or not self._looks_like_gateway(flow):
            return

        # Mitmproxy gives us decoded text
        try:
            body = flow.response.text
            data = json.loads(body)
        except Exception:
            return

        if data.get("protocol") != "Mail_List":
            return

        packet_str = data.get("packet")
        if not isinstance(packet_str, str):
            return

        try:
            packet = json.loads(packet_str)
        except Exception:
            return

        acct_id = self._guess_account_id(packet)
        # Pull outbox
        outbox_url = f"{ADMIN_BASE}/outbox"
        if acct_id is not None:
            outbox_url += f"?accountServerId={acct_id}"
        outbox = _http_get_json(outbox_url)
        if not outbox or not outbox.get("mails"):
            return

        to_add = []
        for qm in outbox["mails"]:
            # If queued mail targets a different account, skip
            target = qm.get("AccountServerId")
            if acct_id is not None and target not in (None, acct_id):
                continue
            to_add.append(self._maildb_from_queued(qm, acct_id))

        if not to_add:
            return

        packet.setdefault("MailDBs", []).extend(to_add)
        packet["Count"] = len(packet["MailDBs"])

        # Write back into the outer wrapper (packet is a JSON **string** field)
        data["packet"] = json.dumps(packet, separators=(",", ":"))
        flow.response.text = json.dumps(data, separators=(",", ":"))
        ctx.log.info(f"[INJECT] Added {len(to_add)} admin mails to Mail_List (acct={acct_id})")

        # Clear if not persistent
        if not outbox.get("persistent"):
            clr_url = f"{ADMIN_BASE}/clear"
            if acct_id is not None:
                clr_url += f"?accountServerId={acct_id}"
            _http_post_json(clr_url, {})

    def response(self, flow: http.HTTPFlow) -> None:
        start_time = getattr(flow, "_start_time", time.time())
        duration_ms = (time.time() - start_time) * 1000
        upstream = "PRIVATE" if state.flipped else "OFFICIAL"

        # Stats & header
        flow.response.headers["x-proxy-upstream"] = upstream
        (state.stats.increment_private if upstream == "PRIVATE" else state.stats.increment_official)()

        # Try injection when not flipped
        try:
            if not state.flipped:
                self._inject_mail(flow)
        except Exception as e:
            ctx.log.warn(f"[INJECT] failed: {e}")

        effective_host = f"{flow.request.host}:{flow.request.port}"
        original_host = flow.request.headers.get("X-Original-Host", flow.request.pretty_host)
        state.logger.log_request({
            "ts": time.time(),
            "method": flow.request.method,
            "original_host": original_host,
            "effective_host": effective_host,
            "path": flow.request.path,
            "status_code": flow.response.status_code,
            "duration_ms": round(duration_ms, 2),
            "upstream": upstream,
        })
        ctx.log.info(f"{flow.request.method} {original_host}{flow.request.path} -> {flow.response.status_code} [{upstream}] ({duration_ms:.0f}ms)")

addons = [BlueArchiveAddon()]
