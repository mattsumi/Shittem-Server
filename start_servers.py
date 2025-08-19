#!/usr/bin/env python3
"""
Startup script for Blue Archive server with C# API integration
"""
import os
import sys
import subprocess
import time
import signal
import threading
from pathlib import Path

def print_colored(text, color_code=0):
    if color_code == 1:  # RED
        print(f"\033[91m{text}\033[0m")
    elif color_code == 2:  # GREEN
        print(f"\033[92m{text}\033[0m")
    elif color_code == 3:  # YELLOW
        print(f"\033[93m{text}\033[0m")
    elif color_code == 4:  # CYAN
        print(f"\033[96m{text}\033[0m")
    else:
        print(text)

def check_dotnet():
    """Check if .NET is installed"""
    try:
        result = subprocess.run(["dotnet", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            version = result.stdout.strip()
            print_colored(f"✓ .NET version: {version}", 2)
            return True
    except FileNotFoundError:
        pass
    
    print_colored("✗ .NET is not installed or not in PATH", 1)
    print_colored("Install .NET 6.0 or later from: https://dotnet.microsoft.com/download", 3)
    return False

def start_csharp_api():
    """Start the C# BlueArchiveAPI server"""
    api_path = Path(__file__).parent / "BlueArchiveAPI"
    csproj_path = api_path / "BlueArchiveAPI" / "BlueArchiveAPI.csproj"
    
    if not csproj_path.exists():
        print_colored("✗ BlueArchiveAPI.csproj not found", 1)
        return None
    
    print_colored("Starting C# BlueArchiveAPI server on port 5000 (HTTPS)...", 4)
    
    env = os.environ.copy()
    # Bind Kestrel to HTTPS 5000 using the same self-signed cert the Python server generates
    cert_dir = Path(__file__).parent / "certs"
    cert_path = cert_dir / "selfsigned_cert.pem"
    key_path = cert_dir / "selfsigned_key.pem"
    env["ASPNETCORE_URLS"] = "https://0.0.0.0:5000;https://0.0.0.0:5100"
    # Kestrel supports PEM + Key via environment
    env["ASPNETCORE_Kestrel__Certificates__Default__Path"] = str(cert_path)
    env["ASPNETCORE_Kestrel__Certificates__Default__KeyPath"] = str(key_path)
    env["DOTNET_ENVIRONMENT"] = env.get("DOTNET_ENVIRONMENT", "Development")
    
    process = subprocess.Popen([
        "dotnet", "run", "--project", str(csproj_path)
    ],
    env=env,
    cwd=str(api_path),
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
    )
    
    return process

def start_python_server():
    """Start the Python proxy server"""
    print_colored("Starting Python proxy server...", 4)
    
    process = subprocess.Popen([
        sys.executable, "blue_archive_server.py"
    ],
    cwd=Path(__file__).parent
    )
    
    return process

def main():
    print_colored("=== Blue Archive Server Startup ===", 4)
    print_colored("Python proxy + C# API integration", 0)
    print()
    
    # Check prerequisites
    if not check_dotnet():
        return 1
    
    processes = []
    
    try:
        # Start Python server first so it can generate/trust the certs
        python_process = start_python_server()
        if python_process:
            processes.append(("Python Server", python_process))
            # Give the Python server a moment to create and trust certs
            time.sleep(5)

        # Start C# API server bound to 5000 HTTPS
        csharp_process = start_csharp_api()
        if csharp_process:
            processes.append(("C# API", csharp_process))
            # Give it time to start
            time.sleep(3)
        
        if not processes:
            print_colored("No servers started", 1)
            return 1
        
        print_colored(f"\n✓ Started {len(processes)} servers", 2)
        print_colored("Press Ctrl+C to stop all servers", 3)
        
        # Monitor processes
        while True:
            time.sleep(1)
            for name, proc in processes:
                if proc.poll() is not None:
                    print_colored(f"✗ {name} stopped unexpectedly", 1)
                    # Dump last lines of output to help diagnose
                    try:
                        if proc.stdout:
                            out = proc.stdout.read()
                            if out:
                                print_colored("--- stdout ---", 4)
                                print(out[-4000:])
                        if proc.stderr:
                            err = proc.stderr.read()
                            if err:
                                print_colored("--- stderr ---", 1)
                                print(err[-4000:])
                    except Exception:
                        pass
                    return 1
                    
    except KeyboardInterrupt:
        print_colored("\nStopping servers...", 3)
        
        for name, proc in processes:
            try:
                proc.terminate()
                proc.wait(timeout=5)
                print_colored(f"✓ Stopped {name}", 2)
            except subprocess.TimeoutExpired:
                proc.kill()
                print_colored(f"✗ Force killed {name}", 1)
            except Exception as e:
                print_colored(f"✗ Error stopping {name}: {e}", 1)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
