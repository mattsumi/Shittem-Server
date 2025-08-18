#!/usr/bin/env python3

import datetime
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
            "prod-noticepool.game.nexon.com",
            "public.api.nexon.com",
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

        entry = {
            "timestamp": timestamp,
            "datetime": str(datetime.datetime.now()),
            "method": request.method,
            "url": request.url,
            "path": request.path,
            "query_string": request.query_string.decode('utf-8', errors='replace'),
            "headers": dict(request.headers),
            "remote_addr": request.remote_addr,
            "user_agent": request.headers.get('User-Agent', 'Unknown'),
            "content_type": request.content_type,
            "content_length": request.content_length,
            "endpoint": endpoint_name,
        }

        try:
            if request.data:
                entry["body"] = request.data.decode('utf-8', errors='replace')
            elif request.is_json:
                entry["body_json"] = request.get_json(silent=True)
            elif request.form:
                entry["form_data"] = dict(request.form)
        except Exception as e:
            entry["body_error"] = str(e)

        filename = f"{self.logs_dir}/{timestamp}_{endpoint_name}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(entry, f, indent=2)

        master_log = f"{self.logs_dir}/all_requests.log"
        with open(master_log, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"[{entry['datetime']}] {entry['method']} {entry['path']}\n")
            f.write(f"User-Agent: {entry['user_agent']}\n")
            f.write(f"Query: {entry['query_string']}\n")
            f.write(f"Headers: {json.dumps(dict(entry['headers']), indent=2)}\n")
            if 'body' in entry:
                f.write(f"Body: {entry['body']}\n")
            f.write(f"{'='*80}\n")

        print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] {request.method} {request.path}")
        print(f"From: {request.remote_addr}")
        print(f"User-Agent: {request.headers.get('User-Agent', 'Unknown')}")
        if request.query_string:
            print(f"Query: {request.query_string.decode('utf-8', errors='replace')}")
        print(f"Saved log: {filename}")

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

    def create_self_signed_cert(self):
        cert_file = "logger_cert.pem"
        key_file = "logger_key.pem"

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
                    xoxb := NameOID.STATE_OR_PROVINCE_NAME,  # keep readable var names; not used
                    x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
                    x509.NameAttribute(NameOID.LOCALITY_NAME, "SF"),
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "BA"),
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
                    .add_extension(
                        x509.SubjectAlternativeName(
                            [
                                x509.DNSName("localhost"),
                                x509.DNSName("127.0.0.1"),
                                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                            ]
                        ),
                        critical=False,
                    )
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

        if cert_file and key_file:
            try:
                context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                context.load_cert_chain(cert_file, key_file)

                print("Starting HTTPS server on port 443.")
                print("Logs directory:", os.path.abspath(self.logs_dir))
                print("Press Ctrl+C to stop.")

                self.app.run(
                    host='0.0.0.0',
                    port=443,
                    ssl_context=context,
                    debug=False,
                    use_reloader=False,
                )

            except Exception as e:
                print(f"HTTPS failed on 443: {e}")
                print("Falling back to HTTP on port 8443.")
                try:
                    self.app.run(
                        host='0.0.0.0',
                        port=8443,
                        debug=False,
                        use_reloader=False,
                    )
                except Exception as e2:
                    print(f"HTTP failed on 8443: {e2}")
                    print("Try running as administrator.")
        else:
            print("Could not create SSL certificate. Using HTTP on 8443.")
            try:
                self.app.run(
                    host='0.0.0.0',
                    port=8443,
                    debug=False,
                    use_reloader=False,
                )
            except Exception as e:
                print(f"HTTP failed on 8443: {e}")
                print("Try running as administrator.")


if __name__ == "__main__":
    logger = BlueArchiveRequestLogger()
    logger.run()
