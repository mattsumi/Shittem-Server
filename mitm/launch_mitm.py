#!/usr/bin/env python3
"""
Blue Archive MITM Proxy Launcher

Launches mitmproxy with the Blue Archive addon, providing clear setup instructions
and configuration validation.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def check_mitmproxy_installed() -> bool:
    """Check if mitmproxy is installed"""
    return shutil.which("mitmdump") is not None


def print_certificate_instructions():
    """Print certificate installation instructions"""
    print("\n" + "="*60)
    print("🔐 CERTIFICATE INSTALLATION REQUIRED")
    print("="*60)
    print()
    print("Before the game will work, you must install the mitmproxy certificate:")
    print()
    print("1. Start mitmproxy (command shown below)")
    print("2. Open a browser and visit: http://mitm.it")
    print("3. Download the certificate for Windows")
    print("4. Install it in 'Trusted Root Certification Authorities'")
    print("   - Right-click certificate file -> Install Certificate")
    print("   - Choose 'Local Machine' -> Next")
    print("   - Select 'Place certificates in the following store'")
    print("   - Browse -> Trusted Root Certification Authorities -> OK")
    print("   - Next -> Finish")
    print()
    print("5. Set Windows system proxy:")
    print("   netsh winhttp set proxy 127.0.0.1:9443")
    print()
    print("6. To remove proxy later:")
    print("   netsh winhttp reset proxy")
    print()
    print("="*60)


def print_usage_instructions():
    """Print usage instructions"""
    print("\n" + "="*60)
    print("🎮 USAGE INSTRUCTIONS")
    print("="*60)
    print()
    print("1. Start your private API server on port 5000 (or set BA_PRIVATE_PORT)")
    print("2. Run the launch command below")
    print("3. Install the mitmproxy certificate (see above)")
    print("4. Set system proxy: netsh winhttp set proxy 127.0.0.1:9443")
    print("5. Start Blue Archive - it should reach main menu using official servers")
    print("6. Visit http://127.0.0.1:9080/_proxy/status to check proxy status")
    print("7. Visit http://127.0.0.1:9080/_proxy/flip to route API calls to private server")
    print("8. Visit http://127.0.0.1:9080/_proxy/unflip to return to official servers")
    print()
    print("Environment variables:")
    print("  BA_PRIVATE_HOST=127.0.0.1    # Private server host")
    print("  BA_PRIVATE_PORT=5000         # Private server port") 
    print("  BA_PRIVATE_SCHEME=http       # Private server scheme")
    print()
    print("="*60)


def main():
    """Main launcher"""
    print("Blue Archive MITM Proxy Launcher")
    print("=" * 40)
    
    # Check if mitmproxy is installed
    if not check_mitmproxy_installed():
        print("❌ ERROR: mitmproxy not found!")
        print()
        print("Please install mitmproxy first:")
        print("  pip install mitmproxy")
        print()
        sys.exit(1)
    
    # Get addon path
    addon_path = Path(__file__).parent / "blue_archive_addon.py"
    if not addon_path.exists():
        print(f"❌ ERROR: Addon not found at {addon_path}")
        sys.exit(1)
    
    # Print instructions
    print_certificate_instructions()
    print_usage_instructions()
    
    # Build command
    cmd = [
        "mitmdump",
        "-s", str(addon_path),
        "--listen-host", "127.0.0.1",
        "--listen-port", "9443",
        "--set", "connection_strategy=lazy",
        "--set", "block_global=false", 
        "--set", "http2=true"
    ]
    
    print("\n" + "="*60)
    print("🚀 STARTING MITMPROXY")
    print("="*60)
    print()
    print("Command:")
    print(" ".join(cmd))
    print()
    print("Proxy will listen on: 127.0.0.1:9443")
    print("Control API will be on: http://127.0.0.1:9080")
    print()
    print("Press Ctrl+C to stop")
    print()
    
    try:
        # Run mitmdump
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\n\n✅ Proxy stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"\n\n❌ Proxy failed with exit code {e.returncode}")
        sys.exit(e.returncode)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()