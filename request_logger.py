#!/usr/bin/env python3

import datetime
import time
import json
import os
import ssl
import sys
import subprocess
import atexit
import signal
from flask import Flask, request


class BlueArchiveRequestLogger:
    def __init__(self):
        self.app = Flask(__name__)
        self.logs_dir = "request_logs"
        self.domains_added = False
        self.setup_logging()
        self.setup_domain_redirects()
        self.setup_routes()
        atexit.register(self.cleanup)
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signum, frame):
        print(f"\nSignal {signum} received. Cleaning up and exiting.")
        self.cleanup()
        sys.exit(0)

    def setup_domain_redirects(self):
        hosts_file = r"C:\Windows\System32\drivers\etc\hosts"
        domains = [
            # Core
            "prod-noticepool.game.nexon.com",
            "public.api.nexon.com",
            # Regional API domains used by Blue Archive
            "nxm-eu-bagl.nexon.com",
            "nxm-ios-bagl.nexon.com",
            "nxm-kr-bagl.nexon.com",
            "nxm-tw-bagl.nexon.com",
            "nxm-th-bagl.nexon.com",
            "nxm-or-bagl.nexon.com",
            # Misc
            "sdk-push.mp.nexon.com",
            "api.nexon.com",
            "game.nexon.com",
            "cdn.nexon.com",
            "patch.nexon.com",
            "auth.nexon.com",
        ]

        print("Setting up domain redirects...")

        try:
            with open(hosts_file, 'r', encoding='utf-8') as f:
                hosts_content = f.read()

            to_add = [d for d in domains if d not in hosts_content]

            if to_add:
                with open(hosts_file, 'a', encoding='utf-8') as f:
                    f.write(f"\n# Blue Archive Request Logger - {datetime.datetime.now()}\n")
                    for domain in to_add:
                        f.write(f"127.0.0.1 {domain}\n")
                self.domains_added = True
                print(f"Added {len(to_add)} domain redirects.")
            else:
                print("All required domain redirects are already present.")

        except PermissionError:
            print("Administrator privileges are required to modify the hosts file.")
            print("Add the following lines manually, then press Enter:")
            for domain in domains:
                print(f"  127.0.0.1 {domain}")
            input()
        except Exception as e:
            print(f"Error setting up domain redirects: {e}")

    def cleanup(self):
        if not self.domains_added:
            return

        print("Cleaning up domain redirects...")
        hosts_file = r"C:\Windows\System32\drivers\etc\hosts"

        try:
            with open(hosts_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            new_lines = []
            skip_section = False

            for line in lines:
                if "Blue Archive Request Logger" in line:
                    skip_section = True
                    continue
                elif skip_section and line.strip() and not line.startswith("127.0.0.1"):
                    skip_section = False

                if not skip_section:
                    new_lines.append(line)

            with open(hosts_file, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)

            print("Domain redirects removed.")
        except Exception as e:
            print(f"Error during cleanup: {e}")

    def setup_logging(self):
        if not os.path.exists(self.logs_dir):
            os.makedirs(self.logs_dir, exist_ok=True)

    def log_request(self, endpoint_name="unknown"):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        # Build a stable, replayable record
        method = request.method
        path = request.path
        query_raw = request.query_string.decode('utf-8', errors='replace')
        host_header = request.headers.get('Host', 'unknown')
        http_version = request.environ.get('SERVER_PROTOCOL', 'HTTP/1.1')

        entry = {
            "timestamp": timestamp,
            "datetime": str(datetime.datetime.now()),
            "method": method,
            "url": request.url,
            "path": path,
            "query_string": query_raw,
            "host": host_header,
            "http_version": http_version,
            "headers": {k: v for k, v in request.headers.items()},
            "remote_addr": request.remote_addr,
            "user_agent": request.headers.get('User-Agent', 'Unknown'),
            "content_type": request.content_type,
            "content_length": request.content_length,
            "endpoint": endpoint_name,
        }

        try:
            raw_body = request.get_data(cache=False) or b''
            if raw_body:
                # Save raw bytes to a .bin alongside metadata; also include base64 inline for convenience
                import base64
                entry["body_base64"] = base64.b64encode(raw_body).decode('ascii')
                entry["body_preview_utf8"] = raw_body[:256].decode('utf-8', errors='replace')
            elif request.is_json:
                entry["body_json"] = request.get_json(silent=True)
            elif request.form:
                entry["form_data"] = dict(request.form)
        except Exception as e:
            entry["body_error"] = str(e)

        base = f"{self.logs_dir}/{timestamp}_{endpoint_name}"
        meta_file = f"{base}.json"
        with open(meta_file, 'w', encoding='utf-8') as f:
            json.dump(entry, f, indent=2)

        # Save raw body if present
        try:
            raw_body = request.get_data(cache=False) or b''
            if raw_body:
                with open(f"{base}.bin", 'wb') as bf:
                    bf.write(raw_body)
        except Exception:
            pass

        # Build a replay helper (PowerShell) that points to the official host and removes hosts overrides for that host
        try:
            official_url = f"https://{host_header}{path}"
            if query_raw:
                official_url += ("?" + query_raw)

            def write_ps(file_path: str, lines: list[str]):
                content = "\n".join(lines) + "\n"
                with open(file_path, 'w', encoding='utf-8') as rf:
                    rf.write(content)

            # Special-case for IAS v3 ticket endpoint: construct JSON { web_token } body
            if path.rstrip('/').endswith('/ias/live/public/v3/issue/ticket/by-web-token'):
                ps = []
                ps.append("#!/usr/bin/env pwsh")
                ps.append("# Auto-generated: v3 ticket replay using JSON body from header/body and robust response capture")
                ps.append("# Tip: run with call operator:  & \"$PSCommandPath\"")
                ps.append("param()")
                ps.append("")
                ps.append(f"$url = '{official_url}'")
                ps.append("$headers = @{}")
                for k, v in request.headers.items():
                    if k.lower() == 'host':
                        ps.append(f"# Host: {v}")
                        continue
                    if k.lower() == 'content-length':
                        continue
                    safe_v = v.replace("'", "''")
                    ps.append(f"$headers['{k}'] = '{safe_v}'")
                # Ensure JSON content type
                ps.append("$headers['Content-Type'] = 'application/json'")
                ps.append("$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path")
                ps.append(f"$bodyFile = Join-Path $scriptDir '{os.path.basename(base)}.bin'")
                ps.append(f"$respFile = Join-Path $scriptDir '{os.path.basename(base)}.response.json'")
                # Hosts cleanup
                ps.append("$uri = [System.Uri]$url")
                ps.append("$targetHost = $uri.Host")
                ps.append("$hostsPath = Join-Path $env:SystemRoot 'System32\\drivers\\etc\\hosts'")
                ps.append("if (Test-Path $hostsPath) { try { $ts = Get-Date -Format 'yyyyMMdd_HHmmss'; $backup = \"$hostsPath.$ts.bak\"; Copy-Item -Path $hostsPath -Destination $backup -Force | Out-Null; $lines = Get-Content -Path $hostsPath -ErrorAction SilentlyContinue; $new = foreach ($l in $lines) { if ($l -match '127\\.0\\.0\\.1' -and $l -match [regex]::Escape($targetHost)) { continue } else { $l } }; Set-Content -Path $hostsPath -Value $new -Encoding UTF8 } catch { Write-Warning \"Failed to adjust hosts file: $($_.Exception.Message)\" } }")
                # Build payload
                ps.append("$token = $null")
                ps.append("if ($headers.ContainsKey('X-Ias-Web-Token')) { $token = $headers['X-Ias-Web-Token'] }")
                ps.append("if (-not $token -and (Test-Path $bodyFile)) { try { $raw = Get-Content -Path $bodyFile -Raw -Encoding Byte; $txt = [System.Text.Encoding]::UTF8.GetString($raw); if ($txt.Trim().StartsWith('{')) { $obj = $txt | ConvertFrom-Json -ErrorAction SilentlyContinue; if ($obj) { $token = $obj.web_token; if (-not $token) { $token = $obj.webToken } } } } catch {} }")
                ps.append("if (-not $token) { Write-Error 'No web_token available to send'; exit 1 }")
                ps.append("$payload = @{ web_token = $token } | ConvertTo-Json -Compress")
                # TLS and request
                ps.append("try { [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12 } catch {}")
                ps.append("$content = $null")
                ps.append("try { $r = Invoke-WebRequest -Method Post -Uri $url -Headers $headers -ContentType 'application/json' -Body $payload -ErrorAction Stop -UseBasicParsing; $content = $r.Content } catch [System.Net.WebException] { if ($_.Exception.Response) { $stream = $_.Exception.Response.GetResponseStream(); if ($stream) { $reader = New-Object System.IO.StreamReader($stream); $content = $reader.ReadToEnd() } } }")
                ps.append("if (-not $content) { try { $handler = New-Object System.Net.Http.HttpClientHandler; $handler.AutomaticDecompression = [System.Net.DecompressionMethods]::GZip -bor [System.Net.DecompressionMethods]::Deflate; $client = New-Object System.Net.Http.HttpClient($handler); $req = New-Object System.Net.Http.HttpRequestMessage([System.Net.Http.HttpMethod]::Post, $url); foreach ($k in $headers.Keys) { if ($k -ne 'Content-Type') { $null = $req.Headers.TryAddWithoutValidation($k, $headers[$k]) } }; $strContent = New-Object System.Net.Http.StringContent($payload, [System.Text.Encoding]::UTF8, 'application/json'); $req.Content = $strContent; $r2 = $client.SendAsync($req).GetAwaiter().GetResult(); $content = $r2.Content.ReadAsStringAsync().GetAwaiter().GetResult() } catch {} }")
                ps.append("if ($content) { $content | Set-Content -Path $respFile -Encoding UTF8; Write-Host 'Saved response to' $respFile; Write-Output $content } else { Write-Error 'No response body received.' }")
                write_ps(f"{base}.replay.ps1", ps)
            else:
                # Generic replay script: send original body if present
                ps_lines = []
                ps_lines.append("# Auto-generated replay script")
                ps_lines.append("# Removes hosts overrides for target host, then replays request with original headers and body")
                ps_lines.append("param()")
                ps_lines.append("")
                ps_lines.append(f"$url = '{official_url}'")
                ps_lines.append("$headers = @{}")
                for k, v in request.headers.items():
                    if k.lower() == 'host':
                        ps_lines.append(f"# Host: {v}")
                    else:
                        safe_v = v.replace("'", "''")
                        ps_lines.append(f"$headers['{k}'] = '{safe_v}'")

                ps_lines.append("$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path")
                ps_lines.append(f"$bodyFile = Join-Path $scriptDir '{os.path.basename(base)}.bin'")
                ps_lines.append(f"$respFile = Join-Path $scriptDir '{os.path.basename(base)}.response.bin'")
                ps_lines.append("$hasBody = Test-Path $bodyFile")
                ps_lines.append("")
                ps_lines.append("$uri = [System.Uri]$url")
                ps_lines.append("$targetHost = $uri.Host")
                ps_lines.append("$hostsPath = Join-Path $env:SystemRoot 'System32\\drivers\\etc\\hosts'")
                ps_lines.append("if (Test-Path $hostsPath) { try { $ts = Get-Date -Format 'yyyyMMdd_HHmmss'; $backup = \"$hostsPath.$ts.bak\"; Copy-Item -Path $hostsPath -Destination $backup -Force | Out-Null; $lines = Get-Content -Path $hostsPath -ErrorAction SilentlyContinue; $new = foreach ($l in $lines) { if ($l -match '127\\.0\\.0\\.1' -and $l -match [regex]::Escape($targetHost)) { continue } else { $l } }; Set-Content -Path $hostsPath -Value $new -Encoding UTF8 } catch { Write-Warning \"Failed to adjust hosts file: $($_.Exception.Message)\" } }")
                ps_lines.append("")
                ps_lines.append("try {")
                ps_lines.append("  if ($hasBody) {")
                ps_lines.append("    $ct = if ($headers.ContainsKey('Content-Type')) { $headers['Content-Type'] } else { 'application/octet-stream' }")
                ps_lines.append(f"    Invoke-WebRequest -Method {method} -Uri $url -Headers $headers -InFile $bodyFile -ContentType $ct -OutFile $respFile -UseBasicParsing")
                ps_lines.append("  } else {")
                ps_lines.append(f"    Invoke-WebRequest -Method {method} -Uri $url -Headers $headers -OutFile $respFile -UseBasicParsing")
                ps_lines.append("  }")
                ps_lines.append("  Write-Host 'Saved response to' $respFile")
                ps_lines.append("} catch { Write-Error $_ }")
                write_ps(f"{base}.replay.ps1", ps_lines)
        except Exception:
            pass

        # If this is the IAS v2 login/link, also build a flow script to call v2 then v3 using the returned web_token
        try:
            if path.rstrip('/').endswith('/ias/live/public/v2/login/link'):
                v2_url = f"https://{host_header}/ias/live/public/v2/login/link"
                v3_url = f"https://{host_header}/ias/live/public/v3/issue/ticket/by-web-token"
                flow_lines = []
                flow_lines.append("# Auto flow: login/link (v2) -> issue ticket by web token (v3)")
                flow_lines.append("param()")
                flow_lines.append(f"$v2 = '{v2_url}'")
                flow_lines.append(f"$v3 = '{v3_url}'")
                flow_lines.append("$headers = @{}")
                for k, v in request.headers.items():
                    if k.lower() == 'host':
                        continue
                    safe_v = v.replace("'", "''")
                    flow_lines.append(f"$headers['{k}'] = '{safe_v}'")
                flow_lines.append("$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path")
                flow_lines.append(f"$bodyFile = Join-Path $scriptDir '{os.path.basename(base)}.bin'")
                flow_lines.append("$hostsPath = Join-Path $env:SystemRoot 'System32\\drivers\\etc\\hosts'")
                flow_lines.append("$removeHost = { param($target) if (Test-Path $using:hostsPath) { try { $lines = Get-Content -Path $using:hostsPath -ErrorAction SilentlyContinue; $new = foreach ($l in $lines) { if ($l -match '127\\.0\\.0\\.1' -and $l -match [regex]::Escape($target)) { continue } else { $l } }; Set-Content -Path $using:hostsPath -Value $new -Encoding UTF8 } catch {} } }")
                flow_lines.append("$h = ($v2 -as [uri]).Host; & $removeHost $h")
                flow_lines.append("try {")
                flow_lines.append("  $ct = if ($headers.ContainsKey('Content-Type')) { $headers['Content-Type'] } else { 'application/json' }")
                flow_lines.append("  $r1 = Invoke-RestMethod -Method Post -Uri $v2 -Headers $headers -ContentType $ct -InFile $bodyFile -UseBasicParsing")
                flow_lines.append("  if (-not $r1.web_token) { throw 'Login/link did not return web_token' }")
                flow_lines.append("  Write-Host 'v2 web_token:' $r1.web_token")
                flow_lines.append("  $headers2 = $headers.Clone()")
                flow_lines.append("  $headers2['Content-Type'] = 'application/json'")
                flow_lines.append("  $body2 = @{ web_token = $r1.web_token } | ConvertTo-Json -Compress")
                flow_lines.append("  $r2 = Invoke-RestMethod -Method Post -Uri $v3 -Headers $headers2 -ContentType 'application/json' -Body $body2 -UseBasicParsing")
                flow_lines.append("  Write-Host 'v3 game_token:' $($r2.game_token)")
                flow_lines.append("  $out = @{ v2=$r1; v3=$r2 } | ConvertTo-Json -Depth 5")
                flow_lines.append(f"  $out | Set-Content -Path (Join-Path $scriptDir '{os.path.basename(base)}.flow.response.json') -Encoding UTF8")
                flow_lines.append("} catch { Write-Error $_ }")
                flow_ps1 = "\n".join(flow_lines) + "\n"
                with open(f"{base}.flow.replay.ps1", 'w', encoding='utf-8') as fr:
                    fr.write(flow_ps1)
        except Exception:
            pass

        master_log = f"{self.logs_dir}/all_requests.log"
        with open(master_log, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"[{entry['datetime']}] {entry['method']} {entry['path']}\n")
            f.write(f"User-Agent: {entry['user_agent']}\n")
            f.write(f"Host: {host_header}\n")
            f.write(f"Query: {entry['query_string']}\n")
            f.write(f"Headers: {json.dumps(dict(entry['headers']), indent=2)}\n")
            if request.content_length and request.content_length > 0:
                f.write(f"Body: {len(request.get_data() or b'')} bytes saved to {base}.bin\n")
            f.write(f"{'='*80}\n")

        print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] {request.method} {request.path}")
        print(f"From: {request.remote_addr}")
        print(f"User-Agent: {request.headers.get('User-Agent', 'Unknown')}")
        if request.query_string:
            print(f"Query: {request.query_string.decode('utf-8', errors='replace')}")
        print(f"Saved log: {meta_file}")

    def setup_routes(self):
        @self.app.route('/com.nexon.bluearchivesteam/server_config/<path:config_file>')
        def server_config(config_file):
            self.log_request(f"server_config_{config_file}")
            return {"status": "logged"}, 200, {'Content-Type': 'application/json'}

        @self.app.route('/prod/crexception-prop')
        def crexception_prop():
            self.log_request("crexception_prop")
            return {"status": "logged"}, 200, {'Content-Type': 'application/json'}

        @self.app.route('/api/<path:endpoint>', methods=['GET', 'POST', 'PUT', 'DELETE'])
        def api_endpoints(endpoint):
            self.log_request(f"api_{endpoint}")
            return {"status": "logged"}, 200, {'Content-Type': 'application/json'}

        @self.app.route('/game/<path:endpoint>', methods=['GET', 'POST', 'PUT', 'DELETE'])
        def game_endpoints(endpoint):
            self.log_request(f"game_{endpoint}")
            return {"status": "logged"}, 200, {'Content-Type': 'application/json'}

        @self.app.route('/protocol/<path:endpoint>', methods=['GET', 'POST', 'PUT', 'DELETE'])
        def protocol_endpoints(endpoint):
            self.log_request(f"protocol_{endpoint}")
            return {"status": "logged"}, 200, {'Content-Type': 'application/json'}

        @self.app.route('/assets/<path:asset>')
        def assets(asset):
            self.log_request(f"assets_{asset}")
            return {"status": "logged"}, 200, {'Content-Type': 'application/json'}

        @self.app.route('/com.nexon.bluearchive/<path:endpoint>', methods=['GET', 'POST', 'PUT', 'DELETE'])
        def ba_mobile_endpoints(endpoint):
            self.log_request(f"ba_mobile_{endpoint}")
            return {"status": "logged"}, 200, {'Content-Type': 'application/json'}

        @self.app.route('/com.nexon.bluearchivesteam/<path:endpoint>', methods=['GET', 'POST', 'PUT', 'DELETE'])
        def ba_steam_endpoints(endpoint):
            self.log_request(f"ba_steam_{endpoint}")
            return {"status": "logged"}, 200, {'Content-Type': 'application/json'}

        @self.app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
        def catch_all(path):
            self.log_request(f"catchall_{path.replace('/', '_')}")
            return {"status": "logged"}, 200, {'Content-Type': 'application/json'}

        @self.app.route('/', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
        def root():
            self.log_request("root")
            return {"status": "logged"}, 200, {'Content-Type': 'application/json'}

        # Parity routes with the main server so the client proceeds
        from flask import Response, jsonify, request as _req

        @self.app.route('/com.nexon.bluearchivesteam/server_config/364258_Live.json', methods=['GET'])
        def server_config_steam():
            self.log_request("server_config_364258_Live")
            server_config = {
                "DefaultConnectionGroup": "live",
                "DefaultConnectionMode": "no",
                "ConnectionGroupsJson": "[\r\n\t{\r\n\t\t\"Name\": \"live\",\r\n\t\t\"OverrideConnectionGroups\": [\r\n\t\t\t{\r\n\t\t\t\t\"Name\": \"global\",\r\n\t\t\t\t\"ApiUrl\": \"https://nxm-eu-bagl.nexon.com:5000/api/\",\r\n\t\t\t\t\"GatewayUrl\": \"https://nxm-eu-bagl.nexon.com:5100/api/\",\r\n\t\t\t\t\"NXSID\": \"live-global\"\r\n\t\t\t}\r\n\t]\r\n\t}]",
                "desc": "1.79.364258"
            }
            return jsonify(server_config)

        @self.app.route('/toy/sdk/getCountry.nx', methods=['POST'])
        def rl_get_country():
            self.log_request("toy_sdk_getCountry")
            country_response = {
                "result": {"country": "GB", "language": "en"},
                "errorCode": 0
            }
            data = json.dumps(country_response).encode('utf-8')
            return Response(data, status=200, headers={
                'Content-Type': 'text/html; charset=UTF-8',
                'Content-Length': str(len(data)),
                'errorcode': '0',
                'access-control-allow-origin': '*',
                'cache-control': 'private',
                'date': datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT'),
                'x-ba-country': 'GB'
            })

        @self.app.route('/api/toy/sdk/getCountry.nx', methods=['POST'])
        def rl_get_country_api():
            return rl_get_country()

        @self.app.route('/toy/sdk/enterToy.nx', methods=['POST'])
        def rl_enter_toy():
            self.log_request("toy_sdk_enterToy")
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
                        "methinksUsage": {"useAlwaysOnRecording": 0, "useScreenshot": 0, "useStreaming": 0, "useSurvey": 0},
                        "livestreamUsage": {"useIM": 0},
                        "useExactAlarmActivation": 0,
                        "useCollectUserActivity": 0,
                        "userActivityDataPushNotification": {"changePoints": [], "notificationType": ""},
                        "appAppAuthLoginIconUrl": "",
                        "useGuidCreationBlk": 0,
                        "guidCreationBlkWlCo": [],
                        "useArena2FA": 0,
                        "usePrimary": 1,
                        "loginUIType": "1",
                        "clientId": "364258",
                        "useMemberships": [101, 103, 110, 107, 9999],
                        "useMembershipsInfo": {"nexonNetSecretKey": "", "nexonNetProductId": "", "nexonNetRedirectUri": ""}
                    },
                    "endBanner": {},
                    "country": "GB",
                    "idfa": {"dialog": [], "imgUrl": "", "language": ""},
                    "useLocalPolicy": ["0", "0"],
                    "enableLogging": False,
                    "enablePlexLogging": False,
                    "enableForcePingLogging": False,
                    "userArenaRegion": 1,
                    "offerwall": {"id": 0, "title": ""},
                    "useYoutubeRewardEvent": False,
                    "gpgCycle": 0,
                    "eve": {"domain": "https://127.0.0.1:443", "g-api": "https://127.0.0.1:443"},
                    "insign": {"useSimpleSignup": 0, "useKrpcSimpleSignup": 0, "useArenaSimpleSignup": 0}
                },
                "errorText": "Success",
                "errorDetail": ""
            }
            return Response(json.dumps(enter_toy_response), status=200, headers={'Content-Type': 'text/html; charset=UTF-8','errorcode':'0','access-control-allow-origin':'*','cache-control':'private','date': datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')})

        @self.app.route('/api/toy/sdk/enterToy.nx', methods=['POST'])
        def rl_enter_toy_api():
            return rl_enter_toy()

        @self.app.route('/toy/sdk/getPromotion.nx', methods=['POST'])
        def rl_get_promotion():
            self.log_request("toy_sdk_getPromotion")
            promotion_response = {"errorCode": 0, "result": {"promotions": [], "banners": []}, "errorText": "Success"}
            return Response(json.dumps(promotion_response), status=200, headers={'Content-Type': 'text/html; charset=UTF-8','errorcode':'0','access-control-allow-origin':'*','cache-control':'private'})

        @self.app.route('/api/toy/sdk/getPromotion.nx', methods=['POST'])
        def rl_get_promotion_api():
            return rl_get_promotion()

        @self.app.route('/prod/crexception-prop', methods=['GET'])
        def rl_crexception_prop():
            self.log_request("prod_crexception_prop")
            return jsonify({"propCheck": True, "period": 10, "ratio": 10})

        # IAS v2 login/link explicit handler
        @self.app.route('/ias/live/public/v2/login/link', methods=['POST'])
        @self.app.route('/api/ias/live/public/v2/login/link', methods=['POST'])
        def rl_ias_v2_login_link():
            self.log_request("ias_live_public_v2_login_link")
            try:
                body = _req.get_json(silent=True) or {}
            except Exception:
                body = {}
            platform = str(body.get('link_platform_type', 'STEAM'))
            try:
                import uuid, time as _t
                now_ms = int(_t.time() * 1000)
                web_token = f"ias:wt:{now_ms}:1247143115@{uuid.uuid4()}@{platform}:ANA"
            except Exception:
                web_token = "ias:wt:0:1247143115@00000000-0000-0000-0000-000000000000@STEAM:ANA"
            local_session_user_id = "76561198000000000"
            lpt = body.get('link_platform_token')
            if isinstance(lpt, str) and len(lpt) > 32:
                import hashlib
                h = hashlib.sha256(lpt.encode('utf-8')).hexdigest()
                base = 76561197960265728
                local_session_user_id = str(base + (int(h[:16], 16) % 10**10))
            return jsonify({
                "web_token": web_token,
                "local_session_type": "arena",
                "local_session_user_id": local_session_user_id,
            })

        @self.app.route('/ias/live/public/v3/issue/ticket/by-web-token', methods=['POST'])
        @self.app.route('/api/ias/live/public/v3/issue/ticket/by-web-token', methods=['POST'])
        def rl_ias_v3_ticket_by_webtoken():
            self.log_request("ias_live_public_v3_issue_ticket_by_web_token")
            try:
                body = _req.get_json(silent=True) or {}
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
                import uuid, time as _t, hashlib
                now_ms = int(_t.time() * 1000)
                game_token = f"ias:gt:{now_ms}:1247143115@{uuid.uuid4()}@{platform}:ANA"
                h = hashlib.sha256((wt or '').encode('utf-8')).hexdigest()
                base = 76561197960265728
                user_id = str(base + (int(h[:16], 16) % 10**10))
            except Exception:
                game_token = "ias:gt:0:1247143115@00000000-0000-0000-0000-000000000000@STEAM:ANA"
                user_id = "76561198000000000"
            return jsonify({
                "game_token": game_token,
                "local_session_type": "arena",
                "local_session_user_id": user_id,
                "expire_in": 3600,
            })

        # IAS token stubs (echo header if present)
        def _extract_token():
            t = _req.headers.get('ias-game-token') or _req.headers.get('IAS-Game-Token')
            if t and t.strip():
                return t.strip()
            try:
                j = _req.get_json(silent=True) or {}
                if isinstance(j, dict):
                    return j.get('webToken') or j.get('token')
            except Exception:
                pass
            return None

        def _webtoken_response(token: str):
            body = {"errorCode": 0, "errorText": "Success", "result": {"webToken": token or "dummy.token.no.sig", "expireIn": 3600}}
            return Response(json.dumps(body), status=200, headers={'Content-Type': 'text/html; charset=UTF-8','errorcode':'0','access-control-allow-origin':'*','cache-control':'private'})

        @self.app.route('/toy/ias/issueWebToken', methods=['POST'])
        @self.app.route('/toy/ias/verifyWebToken', methods=['POST'])
        @self.app.route('/toy/sdk/issueWebToken.nx', methods=['POST'])
        @self.app.route('/toy/sdk/verifyWebToken.nx', methods=['POST'])
        def rl_ias_any():
            self.log_request("ias_webtoken")
            return _webtoken_response(_extract_token())

        @self.app.route('/api/toy/ias/issueWebToken', methods=['POST'])
        @self.app.route('/api/toy/ias/verifyWebToken', methods=['POST'])
        @self.app.route('/api/toy/sdk/issueWebToken.nx', methods=['POST'])
        @self.app.route('/api/toy/sdk/verifyWebToken.nx', methods=['POST'])
        def rl_ias_any_api():
            return rl_ias_any()

    def _logger_hostnames(self):
        return [
            "localhost",
            "127.0.0.1",
            "public.api.nexon.com",
            "prod-noticepool.game.nexon.com",
            "nxm-eu-bagl.nexon.com",
            "nxm-ios-bagl.nexon.com",
            "nxm-kr-bagl.nexon.com",
            "nxm-tw-bagl.nexon.com",
            "nxm-th-bagl.nexon.com",
            "nxm-or-bagl.nexon.com",
        ]

    def create_self_signed_cert(self):
        cert_dir = os.path.join(os.path.dirname(__file__), 'certs')
        os.makedirs(cert_dir, exist_ok=True)
        cert_file = os.path.join(cert_dir, "logger_cert.pem")
        key_file = os.path.join(cert_dir, "logger_key.pem")

        if os.path.exists(cert_file) and os.path.exists(key_file):
            return cert_file, key_file

        print("Creating self-signed certificate...")

        try:
            subprocess.run(
                [
                    "openssl", "req", "-new", "-x509", "-keyout", key_file,
                    "-out", cert_file, "-days", "365", "-nodes",
                    "-subj", "/C=US/ST=CA/L=SF/O=BA/CN=localhost",
                ],
                check=True,
                capture_output=True,
            )
            print("Certificate created with OpenSSL.")
            return cert_file, key_file

        except (subprocess.CalledProcessError, FileNotFoundError):
            print("OpenSSL not available. Falling back to Python.")

            try:
                from cryptography import x509
                from cryptography.x509.oid import NameOID
                from cryptography.hazmat.primitives import hashes
                from cryptography.hazmat.primitives.asymmetric import rsa
                from cryptography.hazmat.primitives import serialization
                import ipaddress

                private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

                subject = issuer = x509.Name([
                    x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                    x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
                    x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "BA Logger"),
                    x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
                ])

                cert = (
                    x509.CertificateBuilder()
                    .subject_name(subject)
                    .issuer_name(issuer)
                    .public_key(private_key.public_key())
                    .serial_number(x509.random_serial_number())
                    .not_valid_before(datetime.datetime.utcnow())
                    .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
                    .add_extension(x509.SubjectAlternativeName([
                        *[x509.DNSName(h) for h in self._logger_hostnames() if not h.replace('.', '').isdigit()],
                        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                    ]), critical=False)
                    .sign(private_key, hashes.SHA256())
                )

                with open(cert_file, "wb") as f:
                    f.write(cert.public_bytes(serialization.Encoding.PEM))

                with open(key_file, "wb") as f:
                    f.write(
                        private_key.private_bytes(
                            encoding=serialization.Encoding.PEM,
                            format=serialization.PrivateFormat.PKCS8,
                            encryption_algorithm=serialization.NoEncryption(),
                        )
                    )

                print("Certificate created with Python cryptography.")
                # Try to trust automatically on Windows
                try:
                    import ctypes
                    if ctypes.windll.shell32.IsUserAnAdmin():
                        subprocess.run(["certutil", "-addstore", "root", cert_file], capture_output=True)
                except Exception:
                    pass
                return cert_file, key_file

            except ImportError:
                print("cryptography library is not installed. Run: pip install cryptography")
                return None, None

    def run(self):
        print("Blue Archive Request Logger")
        print("=" * 50)
        print("This will log all requests and clean up on exit.")
        print("=" * 50)

        try:
            import ctypes
            if not ctypes.windll.shell32.IsUserAnAdmin():
                print("Not running as administrator. Hosts file changes may fail.")
        except Exception:
            pass

        cert_file, key_file = self.create_self_signed_cert()

        # Build SSL context once
        context = None
        if cert_file and key_file:
            try:
                context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                context.load_cert_chain(cert_file, key_file)
            except Exception as e:
                print(f"Failed to init HTTPS context: {e}")
                context = None

        # Start up to three listeners similar to the main server
        def start(port):
            try:
                if context:
                    self.app.run(host='0.0.0.0', port=port, ssl_context=context, debug=False, use_reloader=False)
                else:
                    self.app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
            except Exception as e:
                print(f"Listener {port} failed: {e}")

        print("Logs directory:", os.path.abspath(self.logs_dir))
        print("Starting listeners on 443, 5000, 5100 (HTTPS if possible)")

        import threading
        ports = [443, 5000, 5100]
        threads = []
        for p in ports:
            t = threading.Thread(target=start, args=(p,), daemon=True)
            t.start()
            threads.append(t)

        print("Press Ctrl+C to stop.")
        try:
            while True:
                signal.pause() if hasattr(signal, 'pause') else time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    logger = BlueArchiveRequestLogger()
    logger.run()
