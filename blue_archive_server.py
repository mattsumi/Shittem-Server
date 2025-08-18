import os
import sys
import json
import subprocess
import importlib
from pathlib import Path
from datetime import datetime
import threading
import time
import socket
import platform
import ctypes
import tempfile

RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
MAGENTA = '\033[95m'
CYAN = '\033[96m'
WHITE = '\033[97m'
BOLD = '\033[1m'
RESET = '\033[0m'

def print_colored(text, color=WHITE):
    print(f"{color}{text}{RESET}")

def is_admin():
    try:
        if platform.system() == "Windows":
            return ctypes.windll.shell32.IsUserAnAdmin()
        else:
            return os.geteuid() == 0
    except:
        return False

class HostsManager:
    BLUE_ARCHIVE_DOMAINS = [
        'public.api.nexon.com',
    'prod-noticepool.game.nexon.com',
    # Regional API domains used by Blue Archive
    'nxm-eu-bagl.nexon.com',
    'nxm-ios-bagl.nexon.com',
    'nxm-kr-bagl.nexon.com',
    'nxm-tw-bagl.nexon.com',
    'nxm-th-bagl.nexon.com',
    'nxm-or-bagl.nexon.com',
        'bolo7yechd.execute-api.ap-northeast-1.amazonaws.com',
        'nexon-sdk.nexon.com',
        'api-pub.nexon.com',
        'member.nexon.com',
        'sdk-push.mp.nexon.com',
        'ba.dn.nexoncdn.co.kr',
        'd2vaidpni345rp.cloudfront.net',
        'prod-noticeview.bluearchiveyostar.com',
        'yostarjp.s3-ap-northeast-1.amazonaws.com',
        'yostar-serverinfo.bluearchiveyostar.com',
        'ba-gl-web.bluearchiveyostar.com',
        'ba-gl-kor-web.bluearchiveyostar.com',
        'crash-reporting-api-rs26-usw2.cloud.unity3d.com',
        'uca-cloud-api.cloud.unity3d.com',
        '54.238.121.146',
        'ba-patch.bluearchiveyostar.com',
        'ba-web.bluearchiveyostar.com'
    ]

    def __init__(self):
        if platform.system() == "Windows":
            self.hosts_path = Path(r"C:\Windows\System32\drivers\etc\hosts")
        else:
            self.hosts_path = Path("/etc/hosts")
        self.backup_path = self.hosts_path.parent / "hosts.backup"

    def backup_hosts_file(self):
        try:
            if self.hosts_path.exists() and not self.backup_path.exists():
                import shutil
                shutil.copy2(self.hosts_path, self.backup_path)
                print_colored("Backed up hosts file.", GREEN)
                return True
        except Exception as e:
            print_colored(f"Failed to back up hosts file: {e}", RED)
            return False
        return True

    def read_hosts_file(self):
        try:
            if self.hosts_path.exists():
                return self.hosts_path.read_text(encoding='utf-8')
            return ""
        except Exception as e:
            print_colored(f"Couldn't read hosts file: {e}", YELLOW)
            return ""

    def write_hosts_file(self, content):
        try:
            with open(self.hosts_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            print_colored(f"Failed to write hosts file: {e}", RED)
            print_colored("Run this as administrator.", YELLOW)
            return False

    def add_redirects(self):
        if not is_admin():
            print_colored("Administrator privileges required to edit the hosts file.", RED)
            print_colored("Run this as administrator if you want automatic domain setup.", YELLOW)
            return False

        if not self.backup_hosts_file():
            return False

        current_content = self.read_hosts_file()

        if "# Blue Archive Redirects" in current_content:
            print_colored("Blue Archive redirects already present.", GREEN)
            return True

        redirect_section = "\n# Blue Archive Redirects\n"
        for domain in self.BLUE_ARCHIVE_DOMAINS:
            redirect_section += f"127.0.0.1 {domain}\n"
        redirect_section += "# End Blue Archive Redirects\n"

        new_content = current_content + redirect_section

        if self.write_hosts_file(new_content):
            print_colored(f"Added {len(self.BLUE_ARCHIVE_DOMAINS)} redirect entries.", GREEN)
            return True

        return False

    def remove_redirects(self):
        if not is_admin():
            print_colored("Administrator privileges required to edit the hosts file.", RED)
            return False

        current_content = self.read_hosts_file()

        if "# Blue Archive Redirects" not in current_content:
            print_colored("No Blue Archive redirects found.", GREEN)
            return True

        lines = current_content.split('\n')
        new_lines = []
        skip = False

        for line in lines:
            if "# Blue Archive Redirects" in line:
                skip = True
                continue
            elif "# End Blue Archive Redirects" in line:
                skip = False
                continue
            elif not skip:
                new_lines.append(line)

        new_content = '\n'.join(new_lines)

        if self.write_hosts_file(new_content):
            print_colored("Removed Blue Archive redirect entries.", GREEN)
            return True

        return False

    def show_manual_instructions(self):
        print_colored("\nManual domain redirect setup:", YELLOW)
        print_colored("Add these lines to your hosts file:", WHITE)
        print_colored(f"Location: {self.hosts_path}", CYAN)
        print_colored("", WHITE)
        for domain in self.BLUE_ARCHIVE_DOMAINS:
            print_colored(f"127.0.0.1 {domain}", WHITE)

        print_colored("\nHow to edit the hosts file:", YELLOW)
        print_colored("1) Open a text editor as Administrator.", WHITE)
        print_colored(f"2) Open: {self.hosts_path}", WHITE)
        print_colored("3) Paste the lines shown above.", WHITE)
        print_colored("4) Save.", WHITE)

class DependencyManager:
    REQUIRED_PACKAGES = [
        'flask',
        'requests',
        'flatbuffers',
        'xxhash',
        'pycryptodome',
        'unitypy',
        'cryptography'
    ]

    K0LB3_FILES = {
        'lib/TableEncryptionService.py': 'https://raw.githubusercontent.com/K0lb3s-Datamines/Blue-Archive---Asset-Downloader/main/lib/TableEncryptionService.py',
        'lib/StringCipher.py': 'https://raw.githubusercontent.com/K0lb3s-Datamines/Blue-Archive---Asset-Downloader/main/lib/StringCipher.py',
        'lib/MersenneTwister.py': 'https://raw.githubusercontent.com/K0lb3s-Datamines/Blue-Archive---Asset-Downloader/main/lib/MersenneTwister.py',
        'lib/XXHashService.py': 'https://raw.githubusercontent.com/K0lb3s-Datamines/Blue-Archive---Asset-Downloader/main/lib/XXHashService.py',
        'lib/AESEncryptionService.py': 'https://raw.githubusercontent.com/K0lb3s-Datamines/Blue-Archive---Asset-Downloader/main/lib/AESEncryptionService.py',
        'lib/TableService.py': 'https://raw.githubusercontent.com/K0lb3s-Datamines/Blue-Archive---Asset-Downloader/main/lib/TableService.py',
        'BlueArchive.fbs': 'https://raw.githubusercontent.com/K0lb3s-Datamines/Blue-Archive---Asset-Downloader/main/BlueArchive.fbs'
    }

    def __init__(self):
        self.root_path = Path(__file__).parent

    def check_python_packages(self):
        missing = []
        for package in self.REQUIRED_PACKAGES:
            try:
                importlib.import_module(package.replace('-', '_'))
            except ImportError:
                missing.append(package)
        return missing

    def install_packages(self, packages):
        print_colored(f"Installing {len(packages)} packages...", YELLOW)
        for package in packages:
            print_colored(f"  {package}", CYAN)
            try:
                subprocess.check_call(
                    [sys.executable, '-m', 'pip', 'install', package],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                print_colored(f"  Installed {package}", GREEN)
            except subprocess.CalledProcessError:
                print_colored(f"  Failed to install {package}", RED)
                return False
        return True

    def download_k0lb3_files(self):
        import requests

        missing_files = []
        for rel_path in self.K0LB3_FILES:
            full_path = self.root_path / rel_path
            if not full_path.exists():
                missing_files.append(rel_path)

        if not missing_files:
            print_colored("All protocol files are present.", GREEN)
            return True

        print_colored(f"Downloading {len(missing_files)} protocol files...", YELLOW)

        for rel_path in missing_files:
            full_path = self.root_path / rel_path
            url = self.K0LB3_FILES[rel_path]
            full_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                print_colored(f"  {rel_path}", CYAN)
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                with open(full_path, 'wb') as f:
                    f.write(response.content)
                print_colored(f"  Saved ({len(response.content)} bytes)", GREEN)
            except Exception as e:
                print_colored(f"  Failed: {e}", RED)
                return False

        return True

    def setup_environment(self):
        print_colored("Setting up environment...", BOLD)

        missing_packages = self.check_python_packages()
        if missing_packages:
            if not self.install_packages(missing_packages):
                return False
        else:
            print_colored("Python packages look fine.", GREEN)

        if not self.download_k0lb3_files():
            return False

        print_colored("Environment ready.", GREEN)
        return True

class BlueArchiveServer:
    def __init__(self):
        self.current_version = "1.35.115378"
        self.sessions = {}
        self.player_data = {}
        self.crypto_available = self._setup_crypto()

    def _setup_crypto(self):
        try:
            lib_path = Path(__file__).parent / 'lib'
            if lib_path.exists():
                sys.path.insert(0, str(lib_path))
            import flatbuffers  # noqa: F401
            import xxhash       # noqa: F401
            from Crypto.Util.strxor import strxor  # noqa: F401
            return True
        except ImportError as e:
            print_colored(f"Advanced crypto not available: {e}", YELLOW)
            return False

    def create_flask_app(self):
        try:
            from flask import Flask, request, jsonify, Response
        except ImportError:
            print_colored("Flask isn't installed. Run the dependency setup.", RED)
            return None

        app = Flask(__name__)

        @app.route('/com.nexon.bluearchivesteam/server_config/364258_Live.json', methods=['GET'])
        def server_config():
            self.log_request('/com.nexon.bluearchivesteam/server_config/364258_Live.json')
            server_config = {
                "DefaultConnectionGroup": "live",
                "DefaultConnectionMode": "no",
                "ConnectionGroupsJson": "[\r\n\t{\r\n\t\t\"Name\": \"live\",\r\n\t\t\"OverrideConnectionGroups\": [\r\n\t\t\t{\r\n\t\t\t\t\"Name\": \"global\",\r\n\t\t\t\t\"ApiUrl\": \"https://nxm-eu-bagl.nexon.com:5000/api/\",\r\n\t\t\t\t\"GatewayUrl\": \"https://nxm-eu-bagl.nexon.com:5100/api/\",\r\n\t\t\t\t\"NXSID\": \"live-global\"\r\n\t\t\t}\r\n\t]\r\n\t}]",
                "desc": f"1.79.{self.current_version.split('.')[-1]}"
            }
            print_colored("Server config requested.", BOLD + GREEN)
            return jsonify(server_config)

        @app.route('/toy/sdk/getCountry.nx', methods=['POST'])
        def get_country():
            self.log_request('/toy/sdk/getCountry.nx')
            payload = request.get_data()
            if payload and self.crypto_available:
                self.analyze_flatbuffer_payload(payload)

            country_response = {
                "result": {
                    "country": "GB",
                    "language": "en"
                },
                "errorCode": 0
            }

            data = json.dumps(country_response).encode('utf-8')
            return Response(data, status=200, headers={
                'Content-Type': 'text/html; charset=UTF-8',
                'Content-Length': str(len(data)),
                'errorcode': '0',
                'access-control-allow-origin': '*',
                'cache-control': 'private',
                'date': datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT'),
                'x-ba-country': 'GB'
            })

        # API-prefixed variants used when client applies ApiUrl base
        @app.route('/api/toy/sdk/getCountry.nx', methods=['POST'])
        def get_country_api():
            return get_country()

        @app.route('/prod/crexception-prop', methods=['GET'])
        def crash_exception_prop():
            self.log_request('/prod/crexception-prop')
            config = {
                "propCheck": True,
                "period": 10,
                "ratio": 10
            }
            return jsonify(config)

        @app.route('/api/<path:endpoint>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
        def api_endpoint(endpoint):
            self.log_request(f'/api/{endpoint}')
            print_colored(f"API hit: /api/{endpoint}", BOLD + CYAN)
            return jsonify({
                "errorCode": 0,
                "result": {},
                "message": "OK"
            })

        @app.route('/toy/sdk/enterToy.nx', methods=['POST'])
        def enter_toy():
            self.log_request('/toy/sdk/enterToy.nx')
            payload = request.get_data()
            if payload and self.crypto_available:
                self.analyze_flatbuffer_payload(payload)

            enter_toy_response = {
                "errorCode": 0,
                "result": {
                    "service": {
                        "title": "Blue Archive",
                        "buildVer": "2",
                        "policyApiVer": "2",
                        "termsApiVer": "2",
                        "useTPA": 0,
                        "useGbNpsn": 1,
                        "useGbKrpc": 1,
                        "useGbArena": 1,
                        "useGbJppc": 0,
                        "useGamania": 0,
                        "useToyBanDialog": 0,
                        "grbRating": "",
                        "networkCheckSampleRate": "3",
                        "nkMemberAccessCode": "0",
                        "useIdfaCollection": 0,
                        "useIdfaDialog": 0,
                        "useIdfaDialogNTest": 0,
                        "useNexonOTP": 0,
                        "useRegionLock": 0,
                        "usePcDirectRun": 0,
                        "useArenaCSByRegion": 0,
                        "usePlayNow": 0,
                        "methinksUsage": {
                            "useAlwaysOnRecording": 0,
                            "useScreenshot": 0,
                            "useStreaming": 0,
                            "useSurvey": 0
                        },
                        "livestreamUsage": {
                            "useIM": 0
                        },
                        "useExactAlarmActivation": 0,
                        "useCollectUserActivity": 0,
                        "userActivityDataPushNotification": {
                            "changePoints": [],
                            "notificationType": ""
                        },
                        "appAppAuthLoginIconUrl": "",
                        "useGuidCreationBlk": 0,
                        "guidCreationBlkWlCo": [],
                        "useArena2FA": 0,
                        "usePrimary": 1,
                        "loginUIType": "1",
                        "clientId": "364258",
                        "useMemberships": [101, 103, 110, 107, 9999],
                        "useMembershipsInfo": {
                            "nexonNetSecretKey": "",
                            "nexonNetProductId": "",
                            "nexonNetRedirectUri": ""
                        }
                    },
                    "endBanner": {},
                    "country": "GB",
                    "idfa": {
                        "dialog": [],
                        "imgUrl": "",
                        "language": ""
                    },
                    "useLocalPolicy": ["0", "0"],
                    "enableLogging": False,
                    "enablePlexLogging": False,
                    "enableForcePingLogging": False,
                    "userArenaRegion": 1,
                    "offerwall": {
                        "id": 0,
                        "title": ""
                    },
                    "useYoutubeRewardEvent": False,
                    "gpgCycle": 0,
                    "eve": {
                        "domain": "https://127.0.0.1:443",
                        "g-api": "https://127.0.0.1:443"
                    },
                    "insign": {
                        "useSimpleSignup": 0,
                        "useKrpcSimpleSignup": 0,
                        "useArenaSimpleSignup": 0
                    }
                },
                "errorText": "Success",
                "errorDetail": ""
            }

            print_colored("enterToy called. Initializing.", BOLD + GREEN)

            return Response(json.dumps(enter_toy_response), status=200, headers={
                'Content-Type': 'text/html; charset=UTF-8',
                'errorcode': '0',
                'access-control-allow-origin': '*',
                'cache-control': 'private',
                'date': datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT')
            })

        @app.route('/api/toy/sdk/enterToy.nx', methods=['POST'])
        def enter_toy_api():
            return enter_toy()

        @app.route('/sdk/push/token', methods=['POST'])
        def push_token():
            self.log_request('/sdk/push/token')
            print_colored("Push token registration.", YELLOW)
            return Response('', status=200, headers={
                'Content-Length': '0',
                'Cache-Control': 'no-cache, no-store, max-age=0, must-revalidate',
                'X-XSS-Protection': '1; mode=block',
                'Pragma': 'no-cache',
                'X-Frame-Options': 'DENY',
                'X-Content-Type-Options': 'nosniff'
            })

        @app.route('/toy/sdk/getPromotion.nx', methods=['POST'])
        def get_promotion():
            self.log_request('/toy/sdk/getPromotion.nx')
            payload = request.get_data()
            if payload and self.crypto_available:
                self.analyze_flatbuffer_payload(payload)

            promotion_response = {
                "errorCode": 0,
                "result": {
                    "promotions": [],
                    "banners": []
                },
                "errorText": "Success"
            }

            print_colored("Promotion request.", CYAN)

            return Response(json.dumps(promotion_response), status=200, headers={
                'Content-Type': 'text/html; charset=UTF-8',
                'errorcode': '0',
                'access-control-allow-origin': '*',
                'cache-control': 'private'
            })

        @app.route('/api/toy/sdk/getPromotion.nx', methods=['POST'])
        def get_promotion_api():
            return get_promotion()

        # --- IAS v2 login/link -------------------------------------------------
        @app.route('/ias/live/public/v2/login/link', methods=['POST'])
        @app.route('/api/ias/live/public/v2/login/link', methods=['POST'])
        def ias_login_link():
            self.log_request('/ias/live/public/v2/login/link')
            try:
                body = request.get_json(silent=True) or {}
            except Exception:
                body = {}

            platform = str(body.get('link_platform_type', 'STEAM'))
            # Fabricate a plausible web_token similar to production shape
            try:
                import uuid
                now_ms = int(time.time() * 1000)
                web_token = f"ias:wt:{now_ms}:1247143115@{uuid.uuid4()}@{platform}:ANA"
            except Exception:
                web_token = "ias:wt:0:1247143115@00000000-0000-0000-0000-000000000000@STEAM:ANA"

            # If we can infer a stable user id, keep it; else fallback
            local_session_user_id = "76561198000000000"
            lpt = body.get('link_platform_token')
            if isinstance(lpt, str) and len(lpt) > 32:
                # Derive a deterministic 17-digit number from token for stability
                import hashlib
                h = hashlib.sha256(lpt.encode('utf-8')).hexdigest()
                # Map hex to 17-digit range resembling SteamID64
                as_int = int(h[:16], 16)
                base = 76561197960265728  # SteamID64 base
                local_session_user_id = str(base + (as_int % 10**10))

            resp = {
                "web_token": web_token,
                "local_session_type": "arena",
                "local_session_user_id": local_session_user_id,
            }
            return jsonify(resp)

        # --- IAS v3 ticket by web token ---------------------------------------
        @app.route('/ias/live/public/v3/issue/ticket/by-web-token', methods=['POST'])
        @app.route('/api/ias/live/public/v3/issue/ticket/by-web-token', methods=['POST'])
        def ias_ticket_by_webtoken():
            self.log_request('/ias/live/public/v3/issue/ticket/by-web-token')
            try:
                body = request.get_json(silent=True) or {}
            except Exception:
                body = {}

            wt = body.get('web_token') or body.get('webToken') or ''
            platform = 'STEAM'
            try:
                parts = wt.split('@')
                if len(parts) >= 3:
                    platform = parts[-1].split(':')[0] or 'STEAM'
            except Exception:
                pass

            try:
                now_ms = int(time.time() * 1000)
                # Build a game token similar to production: ias:gt:TIMESTAMP:1247143115@<uuid>@PLATFORM:ANA
                import uuid
                game_token = f"ias:gt:{now_ms}:1247143115@{uuid.uuid4()}@{platform}:ANA"
            except Exception:
                game_token = "ias:gt:0:1247143115@00000000-0000-0000-0000-000000000000@STEAM:ANA"

            user_id = "76561198000000000"
            if wt:
                import hashlib
                h = hashlib.sha256(wt.encode('utf-8')).hexdigest()
                base = 76561197960265728
                user_id = str(base + (int(h[:16], 16) % 10**10))

            resp = {
                "game_token": game_token,
                "local_session_type": "arena",
                "local_session_user_id": user_id,
                "expire_in": 3600,
            }
            return jsonify(resp)

        # --- IAS WebToken stubs -------------------------------------------------
        def _mint_dummy_webtoken(client_id: str = "364258", region: str = "global") -> str:
            try:
                header = {"alg": "none", "typ": "JWT"}
                now = int(time.time())
                payload = {
                    "clientId": client_id,
                    "region": region,
                    "iat": now,
                    "exp": now + 3600,
                    "aud": "blue_archive",
                }
                import base64
                def b64(x):
                    s = json.dumps(x, separators=(',', ':')).encode('utf-8')
                    return base64.urlsafe_b64encode(s).rstrip(b'=').decode('ascii')
                return f"{b64(header)}.{b64(payload)}."  # no signature
            except Exception:
                return "dummy.token.no.sig"

        def _webtoken_response(token: str):
            body = {
                "errorCode": 0,
                "errorText": "Success",
                "result": {
                    "webToken": token,
                    "expireIn": 3600
                }
            }
            data = json.dumps(body).encode('utf-8')
            return Response(data, status=200, headers={
                'Content-Type': 'text/html; charset=UTF-8',
                'Content-Length': str(len(data)),
                'errorcode': '0',
                'access-control-allow-origin': '*',
                'cache-control': 'private'
            })

        def _extract_webtoken_from_request():
            try:
                # Prefer explicit IAS header if present
                hdr = request.headers.get('ias-game-token') or request.headers.get('IAS-Game-Token')
                if hdr and isinstance(hdr, str) and hdr.strip():
                    return hdr.strip()
                if request.is_json:
                    j = request.get_json(silent=True) or {}
                    if isinstance(j, dict):
                        for k in ("token", "webToken", "webtoken"):
                            if k in j and isinstance(j[k], str) and j[k]:
                                return j[k]
                raw = request.get_data() or b''
                if raw:
                    try:
                        j = json.loads(raw.decode('utf-8', errors='ignore'))
                        if isinstance(j, dict):
                            return j.get('webToken') or j.get('token')
                    except Exception:
                        pass
            except Exception:
                pass
            # Fall back to fixed token if configured
            return self.fixed_webtoken

        @app.route('/toy/ias/issueWebToken', methods=['POST'])
        @app.route('/toy/ias/verifyWebToken', methods=['POST'])
        @app.route('/toy/sdk/issueWebToken.nx', methods=['POST'])
        @app.route('/toy/sdk/verifyWebToken.nx', methods=['POST'])
        def ias_webtoken():
            self.log_request('/toy/ias/webtoken')
            token = _extract_webtoken_from_request() or self.fixed_webtoken or _mint_dummy_webtoken()
            return _webtoken_response(token)

        @app.route('/api/toy/ias/issueWebToken', methods=['POST'])
        @app.route('/api/toy/ias/verifyWebToken', methods=['POST'])
        @app.route('/api/toy/sdk/issueWebToken.nx', methods=['POST'])
        @app.route('/api/toy/sdk/verifyWebToken.nx', methods=['POST'])
        def ias_webtoken_api():
            return ias_webtoken()

    # keep existing routes below...

        @app.route('/crash-reporting-api-rs26-usw2.cloud.unity3d.com/api/reporting/v1/projects/<project>/events', methods=['POST'])
        def crash_reporting(project):
            self.log_request(f'/crash-reporting (project: {project})')
            return jsonify({"status": "ok"})

        @app.route('/<path:path>', methods=['GET', 'POST'])
        def catch_all(path):
            self.log_request(f'/{path}')
            print_colored(f"Caught: /{path}", BOLD + MAGENTA)
            return jsonify({"status": "handled", "path": path})

        return app

    def log_request(self, endpoint):
        try:
            from flask import request
            timestamp = datetime.now().strftime('%H:%M:%S')
            method = getattr(request, 'method', 'GET')
            remote_addr = getattr(request, 'remote_addr', 'unknown')
            print_colored(f"[{timestamp}] {method} {endpoint} from {remote_addr}", CYAN)

            if method == 'POST':
                try:
                    payload = request.get_data()
                    if payload:
                        print_colored(f"  Payload: {len(payload)} bytes", BLUE)
                        if self.crypto_available:
                            fb_info = self.analyze_flatbuffer_payload(payload)
                            if fb_info:
                                print_colored(f"  FlatBuffer hint: {fb_info}", MAGENTA)
                except Exception as e:
                    print_colored(f"  Payload analysis failed: {e}", YELLOW)
        except Exception as e:
            print_colored(f"[log error] {endpoint}: {e}", RED)

    def analyze_flatbuffer_payload(self, payload):
        try:
            if not payload or len(payload) < 8:
                return None

            import struct
            offset = struct.unpack('<I', payload[:4])[0]
            if offset >= len(payload):
                return None

            byte_counts = [0] * 256
            sample_size = min(1024, len(payload))
            for b in payload[:sample_size]:
                byte_counts[b] += 1

            total = sum(byte_counts)
            entropy = -sum((count/total) * (count/total).bit_length()
                           for count in byte_counts if count > 0)

            return {
                "size": len(payload),
                "offset": offset,
                "encrypted": entropy > 7.5,
                "entropy": round(entropy, 2)
            }
        except Exception as e:
            print_colored(f"  FlatBuffer analysis failed: {e}", YELLOW)
            return None

    def create_game_config(self):
        return {
            "errorCode": 0,
            "result": {
                "service": {
                    "title": "Blue Archive",
                    "buildVer": self.current_version,
                    "policyApiVer": "2",
                    "termsApiVer": "2",
                    "useTPA": 0,
                    "useGbNpsn": 1,
                    "useGbKrpc": 1,
                    "useGbArena": 1,
                    "usePlayNow": 1,
                    "usePcDirectRun": 1,
                    "clientId": "MjcwOA",
                    "useMemberships": [101, 103, 110, 107, 9999]
                },
                "country": "US",
                "userArenaRegion": 1,
                "enableLogging": False,
                "advanced": {
                    "cryptoSupport": self.crypto_available,
                    "version": self.current_version,
                    "protocolSupport": ["flatbuffer", "xor_encryption", "nexon_api"]
                }
            },
            "errorText": "Success"
        }

    def _load_fixed_webtoken(self):
        # 1) Environment variable takes priority
        tok = os.environ.get('IAS_FIXED_WEBTOKEN')
        if tok and tok.strip():
            print_colored("Using IAS_FIXED_WEBTOKEN from environment.", YELLOW)
            return tok.strip()
        # 2) Fallback: try to read from requests/5.txt (header capture)
        try:
            root = Path(__file__).parent
            p = root / 'requests' / '5.txt'
            if p.exists():
                txt = p.read_text(encoding='utf-8', errors='ignore')
                for line in txt.splitlines():
                    if line.lower().startswith('ias-game-token:'):
                        return line.split(':', 1)[1].strip()
        except Exception:
            pass
        return None

class AntiCheatServer:
    def create_flask_app(self):
        try:
            from flask import Flask, jsonify
        except ImportError:
            return None

        app = Flask(__name__)

        @app.route('/', defaults={'path': ''})
        @app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
        def anti_cheat_handler(path):
            print_colored(f"[AC] /{path}", YELLOW)
            return jsonify({"status": "ok", "anti_cheat": True})

        return app

def check_port_available(port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(('localhost', port))
            return result != 0
    except:
        return False

def _get_ssl_hostnames():
    # Domains the client will connect to; include localhost for manual testing
    hostnames = {
        'localhost',
        '127.0.0.1',
        'public.api.nexon.com',
        'prod-noticepool.game.nexon.com',
        'nxm-eu-bagl.nexon.com',
        'nxm-ios-bagl.nexon.com',
        'nxm-kr-bagl.nexon.com',
        'nxm-tw-bagl.nexon.com',
        'nxm-th-bagl.nexon.com',
        'nxm-or-bagl.nexon.com',
        'crash-reporting-api-rs26-usw2.cloud.unity3d.com',
    }
    return sorted(hostnames)

def _get_cert_paths():
    from pathlib import Path as _Path
    cert_dir = _Path(__file__).parent / 'certs'
    cert_path = cert_dir / 'selfsigned_cert.pem'
    key_path = cert_dir / 'selfsigned_key.pem'
    return cert_path, key_path

def _install_cert_windows(cert_path):
    try:
        if platform.system() != "Windows":
            return False
        if not is_admin():
            print_colored("Admin required to trust certificate automatically.", YELLOW)
            return False
        if not cert_path.exists():
            return False
        # Use certutil to add to Trusted Root Certification Authorities
        result = subprocess.run(["certutil", "-addstore", "root", str(cert_path)], capture_output=True, text=True)
        if result.returncode == 0:
            print_colored("Trusted self-signed certificate in Windows Root store.", GREEN)
            return True
        else:
            print_colored(f"certutil failed: {result.stderr.strip()}", YELLOW)
            return False
    except Exception as e:
        print_colored(f"certutil error: {e}", YELLOW)
        return False

def start_server_thread(app, port, name, use_ssl=False):
    def run_server():
        try:
            if use_ssl:
                ssl_context = create_ssl_context(_get_ssl_hostnames())
                if ssl_context:
                    print_colored(f"{name} server on port {port} (HTTPS)", CYAN)
                    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, ssl_context=ssl_context)
                else:
                    print_colored(f"{name} server on port {port} (HTTP, SSL init failed)", YELLOW)
                    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
            else:
                print_colored(f"{name} server on port {port}", CYAN)
                app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
        except Exception as e:
            print_colored(f"{name} server failed: {e}", RED)

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    return thread

def create_ssl_context(hostnames=None):
    try:
        import ssl
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        import datetime
        import ipaddress
        from pathlib import Path as _Path

        # Reuse persistent cert/key if they exist
        cert_dir = _Path(__file__).parent / 'certs'
        cert_dir.mkdir(exist_ok=True)
        cert_path = cert_dir / 'selfsigned_cert.pem'
        key_path = cert_dir / 'selfsigned_key.pem'

        if cert_path.exists() and key_path.exists():
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(str(cert_path), str(key_path))
            return context

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Blue Archive Server"),
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ])

        # Build SANs including all expected hostnames to satisfy SNI checks
        names = {"localhost", "127.0.0.1"}
        if hostnames:
            names.update(set(hostnames))
        san_entries = []
        for hn in sorted(names):
            try:
                san_entries.append(x509.IPAddress(ipaddress.ip_address(hn)))
            except ValueError:
                san_entries.append(x509.DNSName(hn))

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
            .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
            .sign(private_key, hashes.SHA256())
        )

        # Persist to disk so the certificate can be trusted via Windows cert store
        with open(cert_path, 'wb') as cf:
            cf.write(cert.public_bytes(serialization.Encoding.PEM))
        with open(key_path, 'wb') as kf:
            kf.write(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cert_path), str(key_path))
        return context

    except ImportError:
        print_colored("cryptography isn't installed; HTTPS disabled.", YELLOW)
        return None
    except Exception as e:
        print_colored(f"SSL setup failed: {e}", YELLOW)
        return None

def main():
    print_colored("Blue Archive Private Server", BOLD + CYAN)
    print_colored("=" * 30, CYAN)
    print_colored("Based on K0lb3's protocol notes", CYAN)
    print_colored("=" * 30, CYAN)

    print_colored("\nChecking prerequisites...", YELLOW)

    admin = is_admin()
    if admin:
        print_colored("Running as administrator.", GREEN)
    else:
        print_colored("Not running as administrator.", YELLOW)
        print_colored("Automatic domain setup may fail.", YELLOW)

    print_colored("\nSetting up domain redirects...", YELLOW)
    hosts_manager = HostsManager()

    if admin:
        if hosts_manager.add_redirects():
            print_colored("Domain redirects configured.", GREEN)
        else:
            print_colored("Domain setup failed.", RED)
            hosts_manager.show_manual_instructions()
    else:
        print_colored("Admin rights needed for automatic setup.", YELLOW)
        try:
            response = input("Show manual instructions? (y/n): ").lower().strip()
            if response in ['y', 'yes']:
                hosts_manager.show_manual_instructions()
        except KeyboardInterrupt:
            print_colored("\nSetup cancelled.", YELLOW)
            return 1

    print_colored("\nInstalling dependencies and protocol files...", YELLOW)
    dep_manager = DependencyManager()
    if not dep_manager.setup_environment():
        print_colored("Environment setup failed.", RED)
        input("Press Enter to exit...")
        return 1

    # Ensure certificate exists on disk and try to trust it on Windows
    try:
        ctx = create_ssl_context(_get_ssl_hostnames())
        if ctx is None:
            print_colored("TLS context unavailable; HTTPS may be disabled.", YELLOW)
        cert_path, _ = _get_cert_paths()
        _install_cert_windows(cert_path)
    except Exception as e:
        print_colored(f"Certificate setup step failed: {e}", YELLOW)

    print_colored("\nStarting services...", GREEN)

    ba_server = BlueArchiveServer()
    main_app = ba_server.create_flask_app()

    if not main_app:
        print_colored("Failed to create main server.", RED)
        input("Press Enter to exit...")
        return 1

    ac_server = AntiCheatServer()
    ac_app = ac_server.create_flask_app()

    https_port = 443
    http_port = 80
    ac_port = 58880

    if check_port_available(https_port):
        main_port = https_port
        use_ssl_main = True
        print_colored(f"Using HTTPS port {main_port}.", GREEN)
    elif check_port_available(http_port):
        main_port = http_port
        use_ssl_main = False
        print_colored(f"Using HTTP port {main_port}.", YELLOW)
    else:
        main_port = 8080
        use_ssl_main = False
        print_colored(f"Using fallback port {main_port}.", RED)

    if not check_port_available(ac_port):
        print_colored(f"Port {ac_port} is already in use. Anti-cheat mock may clash.", YELLOW)

    print_colored(f"\nStarting main server on {main_port}...", GREEN)
    main_thread = start_server_thread(main_app, main_port, "Main", use_ssl=use_ssl_main)

    print_colored("Starting API server on 5000...", GREEN)
    # Always use HTTPS for API and Gateway as the client expects TLS on these ports
    api_thread = start_server_thread(main_app, 5000, "API", use_ssl=True)

    print_colored("Starting Gateway server on 5100...", GREEN)
    gateway_thread = start_server_thread(main_app, 5100, "Gateway", use_ssl=True)

    if ac_app:
        print_colored(f"Starting anti-cheat mock on {ac_port}...", GREEN)
        ac_thread = start_server_thread(ac_app, ac_port, "Anti-cheat", use_ssl=False)

    time.sleep(2)

    print_colored("\nServer is up.", BOLD + GREEN)
    print_colored("=" * 30, GREEN)
    protocol = "https" if use_ssl_main else "http"
    print_colored(f"Main:    {protocol}://localhost:{main_port}", CYAN)
    print_colored(f"API:     {protocol}://localhost:5000", CYAN)
    print_colored(f"Gateway: {protocol}://localhost:5100", CYAN)
    if ac_app:
        print_colored(f"AC:      http://localhost:{ac_port}", CYAN)
    print_colored(f"Crypto:  {'enabled' if ba_server.crypto_available else 'basic'}", MAGENTA)
    print_colored(f"Version: {ba_server.current_version}", BLUE)
    print_colored("=" * 30, GREEN)

    print_colored("\nNetwork notes:", CYAN)
    print_colored("The game generally expects HTTPS on 443.", WHITE)

    if admin:
        print_colored("\nSetup complete. Launch the game.", BOLD + GREEN)
    else:
        print_colored("\nManual steps needed:", YELLOW)
        print_colored("1) Configure domain redirects (see above).", WHITE)
        print_colored("2) Launch the game.", WHITE)

    print_colored("3) Watch this console for requests.", WHITE)

    try:
        print_colored("\nCtrl+C to stop.", CYAN)
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print_colored("\nStopping servers...", YELLOW)
        return 0

if __name__ == '__main__':
    sys.exit(main())
