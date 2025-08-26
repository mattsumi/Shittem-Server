#!/usr/bin/env python3
"""
Blue Archive MITM Proxy Addon - Clean Implementation

A minimal, reliable mitmproxy addon that implements runtime flipping of Blue Archive
API traffic to a private server while preserving CDN/static traffic to official servers.

Features:
- Runtime flip/unflip via HTTP control endpoints on :9080
- Structured JSONL logging with daily rotation
- HTTP/2 and WebSocket passthrough (no hacks)
- Response tagging for verification
- Environment variable configuration
- Comprehensive status reporting
"""

import json
import logging
import os
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from mitmproxy import ctx, http


# ---- Configuration ----

# Target domains that should be redirected when flipped
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

# Default private server settings
PRIVATE_HOST: str = os.getenv("BA_PRIVATE_HOST", "127.0.0.1")
PRIVATE_PORT: int = int(os.getenv("BA_PRIVATE_PORT", "7000"))
PRIVATE_SERVER: Tuple[str, int] = (PRIVATE_HOST, PRIVATE_PORT)
PRIVATE_SCHEME: str = os.getenv("BA_PRIVATE_SCHEME", "http")

# Allow domain override via environment
if "BA_TARGET_DOMAINS" in os.environ:
    TARGET_DOMAINS = [d.strip() for d in os.getenv("BA_TARGET_DOMAINS", "").split(",") if d.strip()]

# Logging configuration
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)


class RequestStats:
    """Request statistics tracker"""
    
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
    """Structured JSONL logger with daily rotation"""
    
    def __init__(self):
        self.current_date = None
        self.current_file = None
        self._lock = threading.Lock()
    
    def _get_log_file(self) -> Path:
        """Get current log file, rotating daily"""
        today = datetime.now().strftime("%Y%m%d")
        if today != self.current_date:
            if self.current_file:
                self.current_file.close()
            self.current_date = today
            log_path = LOGS_DIR / f"mitm_{today}.jsonl"
            self.current_file = open(log_path, "a", encoding="utf-8")
        return self.current_file
    
    def log_request(self, entry: Dict):
        """Log a request entry as JSON"""
        with self._lock:
            try:
                log_file = self._get_log_file()
                log_file.write(json.dumps(entry) + "\n")
                log_file.flush()
            except Exception as e:
                ctx.log.error(f"Failed to write JSONL log: {e}")


class SharedState:
    """Shared state for the addon"""
    
    def __init__(self):
        self.flipped: bool = False
        self.stats = RequestStats()
        self.logger = JSONLLogger()
        self._lock = threading.Lock()


# Global state
state = SharedState()


class ControlHandler(BaseHTTPRequestHandler):
    """HTTP handler for control endpoints on :9080"""
    
    def do_GET(self) -> None:
        if self.path == "/_proxy/flip":
            state.flipped = True
            self._send_json({"flipped": True})
            ctx.log.info("Traffic flipping ENABLED - API requests now route to private server")
            return
            
        if self.path == "/_proxy/unflip":
            state.flipped = False
            self._send_json({"flipped": False})
            ctx.log.info("Traffic flipping DISABLED - all requests route to official servers")
            return
            
        if self.path == "/_proxy/health":
            self._send_json({"status": "ok"})
            return
            
        if self.path == "/_proxy/status":
            stats = state.stats.get_stats()
            status_data = {
                "flipped": state.flipped,
                "private_host": PRIVATE_HOST,
                "private_port": PRIVATE_PORT,
                "target_domains": TARGET_DOMAINS,
                "requests_total": stats["requests_total"],
                "private_count": stats["private_count"], 
                "official_count": stats["official_count"],
                "started_at": stats["started_at"],
                "now": time.time(),
            }
            self._send_json(status_data)
            return
        
        # Unknown endpoint
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error": "Not Found"}')
    
    def _send_json(self, data: Dict) -> None:
        """Send JSON response"""
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    
    def log_message(self, format: str, *args) -> None:
        """Suppress default HTTP server logging"""
        pass


def start_control_server() -> None:
    """Start the control HTTP server on port 9080"""
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 9080), ControlHandler)
        ctx.log.info("Control server listening on http://127.0.0.1:9080")
        server.serve_forever()
    except Exception as e:
        ctx.log.error(f"Control server failed to start: {e}")


class BlueArchiveAddon:
    """Main mitmproxy addon for Blue Archive traffic routing"""
    
    def __init__(self):
        self._control_thread_started = False
    
    def load(self, loader) -> None:
        """Load the addon and start control server"""
        if not self._control_thread_started:
            control_thread = threading.Thread(
                target=start_control_server,
                daemon=True,
                name="ControlServer"
            )
            control_thread.start()
            self._control_thread_started = True
            
        ctx.log.info("Blue Archive MITM addon loaded")
        ctx.log.info(f"Target domains: {len(TARGET_DOMAINS)} configured")
        ctx.log.info(f"Private server: {PRIVATE_SCHEME}://{PRIVATE_HOST}:{PRIVATE_PORT}")
        ctx.log.info("Use http://127.0.0.1:9080/_proxy/flip to enable routing")
    
    def request(self, flow: http.HTTPFlow) -> None:
        """Rewrite outgoing requests when flip is enabled and the host matches.

        Enhanced implementation that works with both hostname and raw IP connections.
        When flipped, if the request destination port is 5000 or 5100 OR the SNI/host
        ends with "nxm-" and "-bagl.nexon.com" with those ports, rewrite the flow to
        scheme http, host 127.0.0.1, port 7000, and path /api/gateway, preserving
        method and body. Other domains pass through unchanged.
        """
        # Bail out early if rewriting is not enabled via the flip flag.
        if not state.flipped:
            return
            
        # Retrieve the original host from the request.  This may include an
        # explicit port (e.g. "nxm-eu-bagl.nexon.com:5000" or "192.168.1.1:5000").
        original_host = flow.request.pretty_host
        if not original_host:
            return
            
        # Split off any port from the host for domain matching.
        host_no_port = original_host.split(":", 1)[0].lower()
        original_port = flow.request.port
        sni_host = getattr(flow.request, 'sni', '') or ''
        
        # Check if this should be redirected based on multiple criteria:
        # 1. Target ports 5000 or 5100 (for both hostname and IP connections)
        # 2. SNI/host pattern matching for Blue Archive gateways
        should_redirect = False
        
        # Primary check: ports 5000 or 5100 regardless of hostname
        if original_port in (5000, 5100):
            # Additional validation: check if it's a Blue Archive gateway
            # This works for both domain names and IP addresses that resolve to BA gateways
            is_ba_gateway = (
                any(host_no_port.endswith(domain.lower()) for domain in TARGET_DOMAINS) or
                any(sni_host.lower().endswith(domain.lower()) for domain in TARGET_DOMAINS) or
                # Check for nxm-*-bagl.nexon.com pattern in SNI/host
                (sni_host.startswith('nxm-') and sni_host.endswith('-bagl.nexon.com')) or
                (host_no_port.startswith('nxm-') and host_no_port.endswith('-bagl.nexon.com'))
            )
            should_redirect = is_ba_gateway
        
        if not should_redirect:
            return
        
        # Store original values for logging
        original_full = f"{original_host}:{original_port}"
        original_path = flow.request.path
        
        # Redirect the request to the private API gateway endpoint
        flow.request.scheme = PRIVATE_SCHEME
        flow.request.host = PRIVATE_SERVER[0]
        flow.request.port = PRIVATE_SERVER[1]
        flow.request.path = "/api/gateway"
        
        # Explicitly set the Host header for HTTP/1.1 clients
        flow.request.headers["Host"] = f"{PRIVATE_SERVER[0]}:{PRIVATE_SERVER[1]}"
        
        # Preserve the original host and path for debugging and server processing
        flow.request.headers["X-Original-Host"] = original_host
        flow.request.headers["X-Original-Path"] = original_path
        flow.request.headers["X-Original-Port"] = str(original_port)
        
        # Log the redirection with original and new target
        new_target = f"{PRIVATE_SCHEME}://{PRIVATE_SERVER[0]}:{PRIVATE_SERVER[1]}/api/gateway"
        ctx.log.info(
            f"REDIRECT: {original_full}{original_path} -> {new_target} "
            f"(method: {flow.request.method})"
        )

    
    def response(self, flow: http.HTTPFlow) -> None:
        """Process responses - add upstream tagging and log structured data"""
        start_time = getattr(flow, '_start_time', time.time())
        duration_ms = (time.time() - start_time) * 1000
        
        # Determine which upstream handled this request
        upstream = "OFFICIAL"
        if state.flipped:
            original_host = flow.request.pretty_host
            if original_host:
                host_lower = original_host.lower()
                if any(host_lower.endswith(domain.lower()) for domain in TARGET_DOMAINS):
                    upstream = "PRIVATE"
        
        # Add response header to indicate upstream
        flow.response.headers["x-proxy-upstream"] = upstream
        
        # Update statistics  
        if upstream == "PRIVATE":
            state.stats.increment_private()
        else:
            state.stats.increment_official()
        
        # Get effective host (after any rewriting)
        effective_host = f"{flow.request.host}:{flow.request.port}"
        original_host = flow.request.headers.get("X-Original-Host", flow.request.pretty_host)
        
        # Log structured entry
        log_entry = {
            "ts": time.time(),
            "method": flow.request.method,
            "original_host": original_host,
            "effective_host": effective_host,
            "path": flow.request.path,
            "status_code": flow.response.status_code,
            "duration_ms": round(duration_ms, 2),
            "upstream": upstream
        }
        
        state.logger.log_request(log_entry)
        
        # Log to mitmproxy console
        ctx.log.info(
            f"{flow.request.method} {original_host}{flow.request.path} "
            f"-> {flow.response.status_code} [{upstream}] ({duration_ms:.0f}ms)"
        )


# Export the addon
addons = [BlueArchiveAddon()]