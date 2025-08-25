# Blue Archive mitmproxy Flip Solution

A clean, minimal mitmproxy implementation for flipping Blue Archive API traffic to private servers at runtime.

## Features

- **Runtime flipping**: Switch API traffic routing without restarting the game
- **Preserves CDN traffic**: Only API endpoints are redirected, static assets remain on official servers
- **HTTP/2 and WebSocket support**: Full modern protocol compatibility via mitmproxy
- **Structured logging**: JSONL format with daily rotation for debugging
- **Control API**: Simple HTTP endpoints for flip management
- **Zero admin privileges**: No WinDivert or system-level hooks required

## Requirements

- Python 3.7+
- mitmproxy

## Installation

1. Install mitmproxy:
```bash
pip install mitmproxy
```

2. Install mitmproxy certificate:
```bash
# Run mitmdump once to generate certificates
mitmdump --version

# Install the certificate (Windows)
# The launcher will show you the exact path, typically:
# C:\Users\%USERNAME%\.mitmproxy\mitmproxy-ca-cert.cer
```

3. Configure Windows HTTP proxy:
```cmd
# Set system proxy to mitmproxy (run as administrator)
netsh winhttp set proxy proxy-server="127.0.0.1:9443" bypass-list="<local>"

# To remove proxy later:
netsh winhttp reset proxy
```

## Usage

### Quick Start

```bash
# Run from the mitm directory
python launch_mitm.py
```

This will:
- Start mitmproxy on port 9443 (HTTPS proxy)
- Start control server on port 9080 (HTTP API)
- Show certificate installation instructions
- Begin logging to `logs/ba_proxy_YYYY-MM-DD.jsonl`

### Environment Variables

Configure the private server destination:

```bash
# Private server settings (defaults shown)
set BA_PRIVATE_HOST=127.0.0.1
set BA_PRIVATE_PORT=5000
set BA_PRIVATE_SCHEME=http

# Target domains (comma-separated, defaults shown)
set BA_TARGET_DOMAINS=prod-noticeapi.nexon.com,prod-api.nexon.com,prod-gateway.nexon.com
```

### Control API

#### Get Status
```bash
curl http://localhost:9080/_proxy/status
```
Response:
```json
{
  "flipped": false,
  "target_host": "127.0.0.1:5000",
  "target_scheme": "http",
  "target_domains": ["prod-noticeapi.nexon.com", "prod-api.nexon.com", "prod-gateway.nexon.com"],
  "requests_proxied": 0,
  "uptime_seconds": 123.45
}
```

#### Flip to Private Server
```bash
curl -X POST http://localhost:9080/_proxy/flip
```
Response:
```json
{"status": "flipped", "message": "Traffic now routing to private server"}
```

#### Unflip to Official Servers
```bash
curl -X POST http://localhost:9080/_proxy/unflip
```
Response:
```json
{"status": "unflipped", "message": "Traffic now routing to official servers"}
```

#### Health Check
```bash
curl http://localhost:9080/_proxy/health
```
Response:
```json
{"status": "healthy", "uptime_seconds": 123.45}
```

### Verification

Test the flip functionality:

```bash
python verify_flip.py
```

This will:
1. Check proxy status
2. Make test request (should route to official servers)
3. Flip the proxy
4. Make test request (should route to private server)
5. Unflip the proxy
6. Verify routing is back to official servers

## Logging

Logs are written to `logs/ba_proxy_YYYY-MM-DD.jsonl` in structured JSONL format:

```json
{"timestamp": "2025-01-15T10:30:00.123Z", "level": "INFO", "event": "request_routed", "host": "prod-api.nexon.com", "path": "/api/v1/health", "flipped": true, "upstream": "127.0.0.1:5000"}
{"timestamp": "2025-01-15T10:30:01.234Z", "level": "INFO", "event": "control_request", "endpoint": "/_proxy/flip", "action": "flip"}
```

Log levels:
- `INFO`: Normal operations, request routing, control actions
- `WARNING`: Configuration issues, connection problems
- `ERROR`: Serious errors that prevent operation

## Response Headers

All proxied responses include the `X-Proxy-Upstream` header to indicate routing:
- `X-Proxy-Upstream: official` - Routed to official servers
- `X-Proxy-Upstream: private` - Routed to private server

## Architecture

```
Blue Archive Client
       ↓ (HTTPS via system proxy)
   mitmproxy:9443
       ↓
Blue Archive Addon
   ↓         ↓
Official   Private
Servers    Server
```

### Key Components

- **blue_archive_addon.py**: Main mitmproxy addon with flip logic
- **launch_mitm.py**: Launcher script with proper mitmproxy configuration
- **verify_flip.py**: Verification script for testing functionality

### Target Domains

By default, these Blue Archive API domains are redirected when flipped:
- `prod-noticeapi.nexon.com`
- `prod-api.nexon.com` 
- `prod-gateway.nexon.com`

All other traffic (CDN, static assets, etc.) passes through unchanged.

## Troubleshooting

### Certificate Issues
If you see SSL errors, ensure the mitmproxy certificate is properly installed:
1. Run `mitmdump --version` to generate certificates
2. Install the certificate from `~/.mitmproxy/mitmproxy-ca-cert.cer` 
3. Restart your browser/application

### Proxy Not Working
Check Windows HTTP proxy settings:
```cmd
netsh winhttp show proxy
```
Should show: `Proxy Server(s) :  127.0.0.1:9443`

### Connection Refused
- Ensure mitmproxy is running on port 9443
- Check Windows firewall settings
- Verify no other applications are using port 9443

### Private Server Not Responding
- Check `BA_PRIVATE_HOST` and `BA_PRIVATE_PORT` environment variables
- Verify private server is running and accessible
- Check logs for connection errors

### Game Not Connecting
- Verify certificate is installed and trusted
- Check that only target domains are being redirected
- Review logs for request routing information

## Migration from Old Proxy

The old `blue_archive_server_proxy.py` solution has been completely replaced. Key differences:

| Old Solution | New Solution |
|-------------|-------------|
| Custom aiohttp proxy | mitmproxy framework |
| WinDivert packet capture | Standard HTTPS proxy |
| Admin privileges required | No admin privileges |
| Complex session management | Simple request rewriting |
| Custom TLS handling | mitmproxy built-in TLS |
| Host file manipulation | Environment configuration |
| 1000+ lines of code | <200 lines total |

## Development

To modify the addon:
1. Edit `blue_archive_addon.py`
2. Restart the proxy with `python launch_mitm.py`
3. Test with `python verify_flip.py`

The addon is self-contained with all functionality in a single file.