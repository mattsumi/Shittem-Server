#!/usr/bin/env python3
"""
Blue Archive MITM Proxy
Clean Man-in-the-Middle proxy approach without hosts file modifications.
Game client connects to this proxy which forwards requests transparently.
"""

import os
import sys
import json
import subprocess
import asyncio
import ssl
import time
import platform
import ctypes
import datetime
from pathlib import Path
from urllib.parse import urlparse
from typing import Dict, Any, Optional
import argparse
import signal
import hashlib

# Color codes for terminal output
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
CYAN = '\033[96m'
WHITE = '\033[97m'
BOLD = '\033[1m'
RESET = '\033[0m'

def print_colored(text, color=WHITE):
    """Print colored text to console"""
    print(f"{color}{text}{RESET}")

def is_admin():
    """Check if running with administrator privileges"""
    try:
        if platform.system() == "Windows":
            return ctypes.windll.shell32.IsUserAnAdmin()
        else:
            return os.geteuid() == 0
    except:
        return False

# Install required packages
REQUIRED_PACKAGES = ['aiohttp', 'cryptography', 'brotli', 'pydivert']

def install_missing_packages():
    """Install required packages that are missing"""
    missing = []
    for package in REQUIRED_PACKAGES:
        try:
            if package == 'aiohttp':
                import aiohttp
            elif package == 'cryptography':
                import cryptography
            elif package == 'brotli':
                import brotli
            elif package == 'pydivert':
                import pydivert  # type: ignore
        except ImportError:
            missing.append(package)
    
    if missing:
        print_colored(f"Installing missing packages: {', '.join(missing)}", YELLOW)
        for package in missing:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
    return True

# Install packages and import
install_missing_packages()

import aiohttp
from aiohttp import web, ClientSession, ClientTimeout
import brotli
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import ipaddress
from typing import TYPE_CHECKING

# Optional: Windows transparent redirection via WinDivert (pydivert)
TransparentRedirector = None
RedirectRule = None
_REDIRECT_IMPORT_ERROR: Optional[Exception] = None
if platform.system() == "Windows":
    try:
        from lib.transparent_redirect_win import TransparentRedirector, RedirectRule
    except Exception as e:
        TransparentRedirector = None
        RedirectRule = None
        _REDIRECT_IMPORT_ERROR = e

class SessionManager:
    """Manages per-client session switching state"""
    
    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        
    def get_session_key(self, request) -> str:
        """Generate unique session key from client IP and User-Agent"""
        remote_ip = request.remote or "unknown"
        user_agent = request.headers.get('User-Agent', '')
        session_data = f"{remote_ip}:{user_agent}"
        return hashlib.sha256(session_data.encode()).hexdigest()[:16]
    
    def get_session(self, request) -> Dict[str, Any]:
        """Get or create session for the request"""
        session_key = self.get_session_key(request)
        
        if session_key not in self.sessions:
            self.sessions[session_key] = {
                'switched': False,
                'bootstrap_complete': False,
                'created': time.time(),
                'last_activity': time.time(),
                'request_count': 0
            }
        
        self.sessions[session_key]['last_activity'] = time.time()
        self.sessions[session_key]['request_count'] += 1
        
        return self.sessions[session_key]
    
    def mark_bootstrap_complete(self, request):
        """Mark session as having completed bootstrap"""
        session = self.get_session(request)
        session['bootstrap_complete'] = True
        session['switched'] = True
        print_colored(f"Session {self.get_session_key(request)} bootstrap completed", GREEN)

class HARLogger:
    """Simple HAR logger for request/response tracking"""
    
    def __init__(self):
        self.entries = []
        self.log_file = Path.cwd() / f"blue_archive_mitm_{int(time.time())}.har"
        self._create_initial_file()
        self._last_flush = 0
        
    def _create_initial_file(self):
        """Create initial HAR file"""
        initial_data = {
            "log": {
                "version": "1.2", 
                "creator": {"name": "BlueArchiveMITMProxy", "version": "1.0.0"},
                "entries": []
            }
        }
        
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(initial_data, f, indent=2)
        print_colored(f"HAR log created: {self.log_file}", GREEN)
    
    async def log_request_response(self, request, response, upstream_target: str, 
                                 start_time: float, req_body: bytes = b'', 
                                 resp_body: bytes = b''):
        """Log request and response to HAR format"""
        end_time = time.time()
        duration_ms = int((end_time - start_time) * 1000)
        
        entry = {
            "startedDateTime": datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z'),
            "time": duration_ms,
            "request": {
                "method": request.method,
                "url": str(request.url),
                "headers": [{"name": k, "value": v} for k, v in request.headers.items()],
                "bodySize": len(req_body)
            },
            "response": {
                "status": response.status,
                "statusText": response.reason or "",
                "headers": [{"name": k, "value": v} for k, v in response.headers.items()],
                "bodySize": len(resp_body)
            },
            "_upstream": upstream_target,
            "_mitm": True
        }
        
        self.entries.append(entry)
        print_colored(f"MITM: {request.method} {request.path} -> {upstream_target} ({response.status}) [{duration_ms}ms]", BLUE)
        # Flush to disk every 10 entries
        if len(self.entries) - self._last_flush >= 10:
            self.flush()

    def flush(self):
        try:
            if not self.log_file.exists():
                self._create_initial_file()
            with open(self.log_file, 'r+', encoding='utf-8') as f:
                data = json.load(f)
                data['log']['entries'] = self.entries
                f.seek(0)
                json.dump(data, f, indent=2)
                f.truncate()
            self._last_flush = len(self.entries)
        except Exception as e:
            print_colored(f"Failed to flush HAR log: {e}", YELLOW)

class CertificateManager:
    """SSL certificate management for MITM"""
    
    def __init__(self):
        self.cert_dir = Path.cwd() / 'certs'
        self.cert_dir.mkdir(exist_ok=True)
        self.cert_path = self.cert_dir / 'mitm_proxy_cert.pem'
        self.key_path = self.cert_dir / 'mitm_proxy_key.pem'
        
    def get_ssl_context(self) -> Optional[ssl.SSLContext]:
        """Get or create SSL context for MITM"""
        try:
            if not (self.cert_path.exists() and self.key_path.exists()):
                self._generate_certificates()
            
            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            context.load_cert_chain(str(self.cert_path), str(self.key_path))
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            # Log SNI from clients during TLS handshake so we can see which host the game asks for
            def _sni_logger(sock: ssl.SSLSocket, server_name: str, ssl_ctx: ssl.SSLContext):
                try:
                    host = server_name or "(no-sni)"
                    print_colored(f"[TLS] ClientHello SNI: {host}", CYAN)
                except Exception:
                    pass
            try:
                context.set_servername_callback(_sni_logger)  # type: ignore[attr-defined]
            except Exception:
                # Older Python may not have this; ignore silently
                pass
            
            return context
        except Exception as e:
            print_colored(f"SSL context creation failed: {e}", RED)
            return None
    
    def _generate_certificates(self):
        """Generate MITM SSL certificates"""
        print_colored("Generating MITM SSL certificates...", YELLOW)
        
        # Generate key and certificate
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        
        subject = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Blue Archive MITM Proxy"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Blue Archive MITM"),
        ])
        
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
            .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
            .add_extension(x509.SubjectAlternativeName([
                x509.DNSName("*.nexon.com"),
                x509.DNSName("localhost"),
                x509.DNSName("proxy.local"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            ]), critical=False)
            .sign(key, hashes.SHA256())
        )
        
        # Save certificate and key
        with open(self.cert_path, 'wb') as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
            
        with open(self.key_path, 'wb') as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        print_colored("MITM SSL certificates generated successfully", GREEN)

class BlueArchiveMITMProxy:
    """Clean MITM proxy - no hosts file modifications needed"""
    
    def __init__(self, https_port: int = 9443, http_port: int = 9080,
                 private_upstream: str = "http://127.0.0.1:7000", verbose: bool = False):
        # Ports and upstreams
        self.https_port = https_port
        self.http_port = http_port
        self.private_upstream = private_upstream
        self.official_upstream = "https://nxm-eu-bagl.nexon.com"

        # Managers
        self.session_manager = SessionManager()
        self.har_logger = HARLogger()
        self.cert_manager = CertificateManager()
        self.global_bootstrap_complete = False

        # HTTP client for upstream requests
        self.client_session = None

        # Server instances
        self.https_server = None
        self.http_server = None
        self.shutdown_event = asyncio.Event()

        # Transparent redirector (Windows)
        self.redirector = None

        # Verbose logging flag
        self.verbose = verbose
        
        # REAL Blue Archive Domain Data from nexon_summary.json forensic analysis
        # Complete list of 21 domains actually used by Blue Archive (from HAR traffic analysis)
        self.gateway_hosts = [
            # Primary gateway servers (confirmed in URLs 41-42: ports 5000, 5100)
            "nxm-eu-bagl.nexon.com",
            
            # Main API and authentication servers
            "public.api.nexon.com",
            "signin.nexon.com",
            "config.na.nexon.com",
            
            # NGS services (Nexon Game Security)
            "psm-log.ngs.nexon.com",
            "x-config.ngs.nexon.com",
            "x-csauth.ngs.nexon.com",
            "x-init.ngs.nexon.com",
            "x-update.ngs.nexon.com",
            "accio.ngsm.nexon.com",
            
            # Web interface and CDN
            "bluearchive.nexon.com",
            "ba.dn.nexoncdn.co.kr",
            "jarvis.dn.nexoncdn.co.kr",
            
            # Logging and analytics
            "toy.log.nexon.io",
            "gtable.inface.nexon.com",
            
            # CDN and external services used by Blue Archive
            "d2vaidpni345rp.cloudfront.net",
        ]
        
        # Blue Archive protocol patterns for optimization
        self.ba_api_patterns = [
            '/api/',
            '/toy/sdk/',
            '/toy/log/',
            '/toy/account/',
            '/toy/purchase/',
            '/toy/payment/',
            '/toy/user/',
            '/toy/shop/',
            '/toy/mission/',
            '/toy/raid/',
            '/toy/gacha/',
            '/toy/stage/',
        ]
        
        # BA-specific content types for optimized handling
        self.ba_content_types = {
            'application/json',
            'application/x-protobuf',
            'application/octet-stream',
            'text/plain'
        }
        
        # Connection optimization for BA traffic patterns
        self.ba_connection_limits = {
            'total_connections': 50,  # Reduced from 100 for BA's connection pattern
            'per_host_connections': 10,  # BA typically uses fewer concurrent connections
            'keepalive_timeout': 30,  # BA sessions can be long-lived
            'read_timeout': 15,  # BA API calls are generally fast
        }
        
    async def start(self):
        """Start the MITM proxy servers"""
        print_colored("Blue Archive MITM Proxy Starting...", BOLD + CYAN)
        print_colored("=" * 60, CYAN)
        print_colored("MITM Approach: No hosts file modifications needed!", GREEN)
        print_colored("If transparent redirect is active, no proxy settings change is required.", YELLOW)
        print_colored(f"Local listeners — HTTPS: 127.0.0.1:{self.https_port}  HTTP: 127.0.0.1:{self.http_port}", WHITE)
        print_colored("=" * 60, CYAN)
        
        # Create Blue Archive optimized HTTP client for upstream requests
        ba_timeout = ClientTimeout(
            total=self.ba_connection_limits['keepalive_timeout'],
            connect=15,
            sock_read=self.ba_connection_limits['read_timeout']
        )
        ba_connector = aiohttp.TCPConnector(
            limit=self.ba_connection_limits['total_connections'],
            limit_per_host=self.ba_connection_limits['per_host_connections'],
            enable_cleanup_closed=True,
            keepalive_timeout=self.ba_connection_limits['keepalive_timeout'],
            # Blue Archive specific TCP optimization
            use_dns_cache=True,
            ttl_dns_cache=300,  # Cache DNS for 5 minutes for BA hosts
        )
        self.client_session = ClientSession(
            timeout=ba_timeout,
            connector=ba_connector
        )
        
        # Setup graceful shutdown
        for sig in [signal.SIGINT, signal.SIGTERM]:
            signal.signal(sig, self._signal_handler)
        
    # Start servers
        success = await self._start_servers()
        if not success:
            return False
        
    # Prepare transparent redirector (idle at start; manual flip to enable)
        if platform.system() == "Windows":
            if TransparentRedirector is None:
                detail = f" ({_REDIRECT_IMPORT_ERROR})" if _REDIRECT_IMPORT_ERROR else ""
                print_colored(f"WinDivert redirector import failed; transparent redirect disabled{detail}.", YELLOW)
            elif not is_admin():
                print_colored("Run as Administrator to enable transparent redirect (WinDivert).", YELLOW)
            else:
                try:
                    self.redirector = TransparentRedirector(rules=[], debug=self.verbose)
                    self.redirector.start()  # Original version uses sync start
                    print_colored("Transparent redirect: IDLE (use /_proxy/flip to enable)", CYAN)
                except Exception as e:
                    print_colored(f"Failed to start transparent redirector: {e}", YELLOW)
                    if self.verbose:
                        import traceback
                        print_colored(f"Redirector error traceback: {traceback.format_exc()}", RED)

        print_colored("MITM proxy started successfully!", BOLD + GREEN)
        print_colored("=" * 60, GREEN)
        if platform.system() == "Windows" and self.redirector:
            print_colored("Transparent redirect: IDLE — no traffic intercepted until flip", CYAN)
        else:
            print_colored("Transparent redirect: DISABLED — you may need to set system proxy.", YELLOW)
        print_colored(f"HTTPS listener: 127.0.0.1:{self.https_port}", CYAN)
        print_colored(f"HTTP listener:  127.0.0.1:{self.http_port}", CYAN)
        print_colored("", WHITE)
        print_colored("Usage:", YELLOW)
        print_colored("1) Install the generated MITM certificate into Trusted Root CAs", WHITE)
        print_colored("2) Start the game. If redirect is disabled, set Windows proxy temporarily.", WHITE)
        print_colored("", WHITE)
        print_colored("Press Ctrl+C to stop...", CYAN)
        
        await self.shutdown_event.wait()
        return True
    
    async def _start_servers(self):
        """Start HTTPS and HTTP proxy servers"""
        try:
            # HTTPS Proxy Server
            https_app = web.Application()
            https_app.router.add_get('/_proxy/health', self._handle_health)
            https_app.router.add_get('/_proxy/status', self._handle_status)
            https_app.router.add_get('/_proxy/flip', self._handle_flip)
            https_app.router.add_get('/_proxy/unflip', self._handle_unflip)
            https_app.router.add_route('*', '/{path:.*}', self._handle_https_request)
            
            ssl_context = self.cert_manager.get_ssl_context()
            if ssl_context:
                https_runner = web.AppRunner(https_app, access_log=None)
                await https_runner.setup()
                
                https_site = web.TCPSite(
                    https_runner, 
                    '127.0.0.1', 
                    self.https_port, 
                    ssl_context=ssl_context
                )
                await https_site.start()
                self.https_server = https_runner
                print_colored(f"HTTPS proxy bound to 127.0.0.1:{self.https_port}", GREEN)
            
            # HTTP Proxy Server  
            http_app = web.Application()
            http_app.router.add_get('/_proxy/flip', self._handle_flip)
            http_app.router.add_get('/_proxy/unflip', self._handle_unflip)
            http_app.router.add_route('*', '/{path:.*}', self._handle_http_request)
            
            http_runner = web.AppRunner(http_app, access_log=None)
            await http_runner.setup()
            
            http_site = web.TCPSite(http_runner, '127.0.0.1', self.http_port)
            await http_site.start()
            self.http_server = http_runner
            print_colored(f"HTTP proxy bound to 127.0.0.1:{self.http_port}", GREEN)
            
            return True
            
        except Exception as e:
            print_colored(f"Server startup failed: {e}", RED)
            return False

    async def _handle_flip(self, request):
        """Manually enable redirect rules and switch to private upstream"""
        self.global_bootstrap_complete = True
        if platform.system() == "Windows" and self.redirector and RedirectRule:
            try:
                self._enable_gateway_redirect_rules()
                print_colored("Transparent redirect: ENABLED (manual flip)", GREEN)
                return web.json_response({"status": "ok", "flipped": True})
            except Exception as e:
                print_colored(f"Failed to enable redirect rules: {e}", YELLOW)
                if self.verbose:
                    import traceback
                    print_colored(f"Flip error traceback: {traceback.format_exc()}", RED)
                return web.json_response({"status": "error", "error": str(e)}, status=500)
        return web.json_response({"status": "ok", "note": "redirector not available"})

    async def _handle_unflip(self, request):
        """Disable redirect rules and return to official upstream"""
        self.global_bootstrap_complete = False
        if platform.system() == "Windows" and self.redirector:
            try:
                self.redirector.update_rules([])  # This is NOT an async method
                print_colored("Transparent redirect: DISABLED (manual unflip)", YELLOW)
                return web.json_response({"status": "ok", "flipped": False})
            except Exception as e:
                print_colored(f"Failed to disable redirect rules: {e}", YELLOW)
                if self.verbose:
                    import traceback
                    print_colored(f"Unflip error traceback: {traceback.format_exc()}", RED)
                return web.json_response({"status": "error", "error": str(e)}, status=500)
        return web.json_response({"status": "ok", "note": "redirector not available"})
    
    async def _handle_https_request(self, request):
        """Handle HTTPS requests through MITM proxy"""
        return await self._handle_proxy_request(request, "HTTPS")
    
    async def _handle_http_request(self, request):
        """Handle HTTP requests through proxy"""
        return await self._handle_proxy_request(request, "HTTP")
    
    async def _handle_proxy_request(self, request, protocol):
        """Main MITM proxy request handler"""
        start_time = time.time()
        if self.verbose:
            print_colored(f"[IN] {protocol} {request.method} {request.host}{request.path_qs}", CYAN)
            for k, v in request.headers.items():
                print(f"    > {k}: {v}")
        
        try:
            # Handle favicon requests locally to avoid annoying backend errors
            if request.path == '/favicon.ico':
                return web.Response(status=204)  # No Content - browsers will stop asking
            
            # Get session for this client
            session = self.session_manager.get_session(request)
            
            # Determine upstream based on routing rules
            upstream = self._determine_upstream(request, session)
            
            # Read request body
            req_body = await request.read() if request.can_read_body else b''
            
            # Forward request through MITM
            response = await self._forward_request(request, upstream, req_body)
            
            # Check for bootstrap completion
            await self._check_bootstrap_completion(request, response, req_body)
            
            # Log to HAR (only log non-intercepted when verbose)
            resp_body = getattr(response, 'body', b'')
            if self.verbose or upstream == self.private_upstream:
                await self.har_logger.log_request_response(
                    request, response, upstream, start_time, req_body, resp_body
                )
            
            # Console logging
            duration = (time.time() - start_time) * 1000
            remote_ip = request.remote or "unknown"
            color = GREEN if 200 <= response.status < 300 else YELLOW if response.status < 400 else RED
            print_colored(f"[{protocol}] [{remote_ip}] {request.method} {request.path} → {response.status} [{duration:.0f}ms]", color)
            if self.verbose:
                for k, v in response.headers.items():
                    print(f"    < {k}: {v}")
            
            return response
            
        except Exception as e:
            print_colored(f"MITM request handling error: {e}", RED)
            return web.Response(
                status=502,
                text=json.dumps({"error": "MITM proxy error", "details": str(e)}),
                headers={'Content-Type': 'application/json'}
            )
    
    def _determine_upstream(self, request, session: Dict[str, Any]) -> str:
        """Determine which upstream to route to with Blue Archive specific optimizations"""
        path = request.path.lower()
        host = request.host.lower() if request.host else ""

        # Blue Archive specific routing logic
        is_ba_api = any(pattern in path for pattern in self.ba_api_patterns)
        is_ba_host = any(ba_host in host for ba_host in self.gateway_hosts)
        
        # If globally flipped, keep game on private for any captured BA traffic
        if self.global_bootstrap_complete:
            if is_ba_host or is_ba_api:
                # Mark this session as handling BA traffic for optimization
                session['is_ba_traffic'] = True
                return self.private_upstream
            return self.private_upstream

        # Blue Archive specific bootstrap handling
        # Do not intercept public.api.nexon.com until bootstrap success
        if host.endswith("public.api.nexon.com") and not session['bootstrap_complete']:
            return self.official_upstream

        # Priority routing for BA API patterns
        if is_ba_api:
            session['is_ba_traffic'] = True
            return self.private_upstream
        
        # All /api/ requests go to private upstream after bootstrap or if they are our API
        if "/api/" in path:
            return self.private_upstream
        
        # For non-API requests, check session state
        if session['switched'] or session['bootstrap_complete']:
            return self.private_upstream
        else:
            return self.official_upstream
    
    async def _forward_request(self, request, upstream: str, req_body: bytes):
        """Forward request through MITM to upstream with Blue Archive optimizations"""
        # Build target URL: for private, use private_upstream; for official, use the original host/scheme
        if upstream == self.private_upstream:
            target_base = self.private_upstream
        else:
            scheme = request.scheme or urlparse(self.official_upstream).scheme or "https"
            host = request.host or urlparse(self.official_upstream).netloc
            target_base = f"{scheme}://{host}"
        target_url = f"{target_base}{request.path_qs}"
        
        # Blue Archive specific header optimization
        headers = {}
        hop_by_hop = {'connection', 'keep-alive', 'proxy-authenticate',
                     'proxy-authorization', 'te', 'trailers', 'transfer-encoding', 'upgrade'}
        
        # Preserve important Blue Archive headers
        ba_important_headers = {
            'user-agent', 'x-nexon-cc', 'x-nexon-language', 'x-nexon-device-id',
            'x-nexon-client-version', 'authorization', 'content-type'
        }
        
        for key, value in request.headers.items():
            key_lower = key.lower()
            if key_lower not in hop_by_hop:
                # Prioritize BA important headers
                if key_lower in ba_important_headers or not key_lower.startswith('x-'):
                    headers[key] = value
                elif key_lower.startswith('x-nexon') or key_lower.startswith('x-unity'):
                    # Keep all Nexon and Unity specific headers for BA compatibility
                    headers[key] = value
                else:
                    headers[key] = value
        
        # Set appropriate Host header
        if upstream == self.private_upstream:
            headers['Host'] = urlparse(self.private_upstream).netloc
        else:
            headers['Host'] = request.host or urlparse(self.official_upstream).netloc
        
        # Blue Archive specific optimizations
        is_ba_request = any(pattern in request.path.lower() for pattern in self.ba_api_patterns)
        content_type = request.headers.get('content-type', '').lower()
        is_ba_content = any(ct in content_type for ct in self.ba_content_types)
        
        try:
            if self.verbose:
                print_colored(f"MITM forwarding to: {target_url}", CYAN)
            
            # Blue Archive optimized request handling
            ssl_verify = upstream != self.private_upstream
            
            # Adjust timeout for BA requests (they can be slightly longer for complex operations)
            request_timeout = None
            if is_ba_request:
                if 'gacha' in request.path.lower() or 'purchase' in request.path.lower():
                    # Gacha and purchase operations may take longer
                    request_timeout = ClientTimeout(total=45, sock_read=30)
                elif 'stage' in request.path.lower() or 'raid' in request.path.lower():
                    # Combat operations need more time
                    request_timeout = ClientTimeout(total=60, sock_read=45)
            
            async with self.client_session.request(
                method=request.method,
                url=target_url,
                headers=headers,
                data=req_body,
                ssl=ssl_verify,
                allow_redirects=False,
                timeout=request_timeout  # Use BA-specific timeout if set
            ) as upstream_response:
                
                # Read response body
                response_body = await upstream_response.read()
                
                # Build response headers
                response_headers = {}
                for key, value in upstream_response.headers.items():
                    if key.lower() not in hop_by_hop:
                        response_headers[key] = value
                
                # Blue Archive optimized compression handling
                content_encoding = upstream_response.headers.get('Content-Encoding', '').lower()
                if content_encoding == 'br':
                    try:
                        response_body = brotli.decompress(response_body)
                        response_headers.pop('Content-Encoding', None)
                        # Update content length for BA clients
                        response_headers['Content-Length'] = str(len(response_body))
                    except Exception as e:
                        if self.verbose:
                            print_colored(f"Brotli decompression failed for BA request: {e}", YELLOW)
                elif content_encoding == 'gzip' and is_ba_content:
                    # BA sometimes uses gzip, handle it properly
                    try:
                        import gzip
                        response_body = gzip.decompress(response_body)
                        response_headers.pop('Content-Encoding', None)
                        response_headers['Content-Length'] = str(len(response_body))
                    except Exception as e:
                        if self.verbose:
                            print_colored(f"Gzip decompression failed for BA request: {e}", YELLOW)
                
                response = web.Response(
                    body=response_body,
                    status=upstream_response.status,
                    headers=response_headers
                )
                
                # Store body for logging
                response.body = response_body
                if self.verbose:
                    print_colored(f"Upstream responded {upstream_response.status} for {target_url}", CYAN)
                return response
                
        except Exception as e:
            print_colored(f"MITM forward request failed: {e}", RED)
            return web.Response(
                status=502,
                text=json.dumps({
                    "error": "MITM upstream failed", 
                    "upstream": upstream,
                    "details": str(e),
                    "note": "Configure game client to use this proxy"
                }),
                headers={'Content-Type': 'application/json'}
            )
    
    async def _check_bootstrap_completion(self, request, response, req_body: bytes):
        """Check if bootstrap completion marker is detected"""
        rpath = request.path.lower()
        rhost = (request.host or "").lower()
        if "/toy/sdk/getpromotion.nx" in rpath and request.method.upper() == "POST":
            try:
                if response.status == 200:
                    # First prefer the header that Nexon sets: errorcode: 0
                    hdr_err = None
                    for k, v in response.headers.items():
                        if k.lower() == 'errorcode':
                            hdr_err = v.strip()
                            break
                    is_success = (hdr_err == '0')
                    if hdr_err is not None:
                        print_colored(f"getPromotion.nx header errorcode={hdr_err}", CYAN)

                    # If header missing, attempt JSON parse as fallback
                    if not is_success and hasattr(response, 'body') and response.body:
                        try:
                            response_text = response.body.decode('utf-8')
                            response_data = json.loads(response_text)
                            is_success = (response_data.get('errorCode') == 0)
                        except Exception:
                            is_success = False

                    if is_success:
                        print_colored("Bootstrap getPromotion.nx success detected (errorCode=0)", GREEN)
                        self.session_manager.mark_bootstrap_complete(request)
                        self.global_bootstrap_complete = True
                        # If redirector exists, enable BA rules now
                        if platform.system() == "Windows" and self.redirector and RedirectRule:
                            try:
                                self._enable_gateway_redirect_rules()
                                print_colored("Transparent redirect: ENABLED after bootstrap", GREEN)
                            except Exception as e:
                                print_colored(f"Failed to enable redirect rules: {e}", YELLOW)
                                if self.verbose:
                                    import traceback
                                    print_colored(f"Bootstrap redirect error traceback: {traceback.format_exc()}", RED)
                    else:
                        print_colored("Bootstrap detection: getPromotion.nx did not indicate success (no header or non-zero)", YELLOW)
            except:
                pass
    
    async def _handle_health(self, request):
        """Health check endpoint"""
        return web.json_response({
            "status": "healthy",
            "proxy_type": "MITM",
            "sessions": len(self.session_manager.sessions),
            "requests_logged": len(self.har_logger.entries)
        })
    
    async def _handle_status(self, request):
        """Status endpoint"""
        redirector_status = "disabled"
        redirector_details = {}
        
        if platform.system() == "Windows" and self.redirector:
            try:
                redirector_status = "enabled"
                # Get enhanced redirector metrics if available
                if hasattr(self.redirector, 'get_metrics'):
                    metrics = self.redirector.get_metrics()
                    redirector_details = {
                        "active_rules": len(self.redirector.rules) if hasattr(self.redirector, 'rules') else 0,
                        "packets_processed": metrics.get('packets_processed', 0),
                        "dns_cache_size": metrics.get('dns_cache_size', 0),
                        "uptime_seconds": metrics.get('uptime_seconds', 0)
                    }
                else:
                    redirector_details = {"active_rules": "unknown"}
            except Exception as e:
                redirector_status = f"error: {e}"
        
        return web.json_response({
            "proxy_type": "Blue Archive MITM (Man-in-the-Middle)",
            "https_port": self.https_port,
            "http_port": self.http_port,
            "private_upstream": self.private_upstream,
            "official_upstream": self.official_upstream,
            "sessions": len(self.session_manager.sessions),
            "har_entries": len(self.har_logger.entries),
            "flipped": self.global_bootstrap_complete,
            "redirector_status": redirector_status,
            "redirector_details": redirector_details,
            "configuration": {
                "https_proxy": f"127.0.0.1:{self.https_port}",
                "http_proxy": f"127.0.0.1:{self.http_port}",
                "no_hosts_modification": True,
                "enhanced_redirect": False  # Using original working version
            }
        })

    def _enable_gateway_redirect_rules(self):
        """Enable redirect rules for Blue Archive - FOCUSED on critical gateway only"""
        if not (platform.system() == "Windows" and self.redirector and RedirectRule):
            return
        
        # CRITICAL FIX: Only redirect the PRIMARY gateway that needs transparent redirection
        # From nexon_summary.json URLs 41-42: nxm-eu-bagl.nexon.com:5000/5100
        # All other domains work fine through normal proxy settings (HTTPS/443)
        gateway_rule = RedirectRule(
            ports=[5000, 5100],  # Only the non-standard ports need transparent redirect
            to_port=self.https_port,
            domains=["nxm-eu-bagl.nexon.com"]  # Only 1 domain = ~2 IPs vs 31 IPs
        )
        
        rules = [gateway_rule]
        
        # Update IPs for the rule (original working approach)
        for rule in rules:
            rule.update_ips()
        
        print_colored(f"Enabling transparent redirect for PRIMARY Blue Archive gateway only (filter optimization)", CYAN)
        if self.verbose:
            for rule in rules:
                print_colored(f"  Gateway Rule: {rule.domains[0]}, ports {rule.ports} -> {rule.to_port} (IPs: {len(rule._ip_cache)})", CYAN)
                print_colored(f"  Note: Other domains use standard HTTPS/443 via proxy settings", CYAN)
        
        self.redirector.update_rules(rules)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print_colored("\nReceived shutdown signal...", YELLOW)
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        if loop.is_running():
            loop.create_task(self._shutdown())
        else:
            loop.run_until_complete(self._shutdown())
    
    async def _shutdown(self):
        """Graceful shutdown"""
        print_colored("Shutting down MITM proxy...", YELLOW)
        
        # Close client session
        if self.client_session:
            await self.client_session.close()
        
        # Close servers
        if self.https_server:
            await self.https_server.cleanup()
        
        if self.http_server:
            await self.http_server.cleanup()
        # Stop redirector
        if self.redirector:
            try:
                self.redirector.stop()  # This is NOT an async method
                print_colored("Redirector stopped successfully", GREEN)
            except Exception as e:
                print_colored(f"Redirector shutdown issue: {e}", YELLOW)
                if self.verbose:
                    import traceback
                    print_colored(f"Shutdown error traceback: {traceback.format_exc()}", RED)
        try:
            self.har_logger.flush()
        except Exception:
            pass
        
        print_colored("MITM proxy shutdown complete", GREEN)
        self.shutdown_event.set()

async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Blue Archive MITM Proxy")
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose logging of all traffic and headers')
    args = parser.parse_args()

    print_colored("Blue Archive MITM Proxy", BOLD + CYAN)
    print_colored("Clean proxy approach without hosts file modifications", CYAN)
    
    proxy = BlueArchiveMITMProxy(verbose=args.verbose)
    
    try:
        await proxy.start()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print_colored(f"Fatal error: {e}", RED)
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))