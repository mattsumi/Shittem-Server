Blue Archive MITM + Private Server (work-in-progress)

This spins up:
- An ASP.NET Core API (private server backend)
- A Python MITM proxy that cleanly hijacks the game after you flip it

Yes, you need the TLS patch. No, the game won’t just “trust” your proxy on its own.

## Requirements
- Windows 10/11 (run things as Administrator when told)
- .NET 6 SDK
- Python 3.11+ (3.13 is fine)
- The game client + the included ClientHook (DLL injection)

## Quick start
1) Start the API on port 7000
- Open `BlueArchiveAPI/BlueArchiveAPI`
- Run it pinned to 7000 so the proxy can find it:

	PowerShell:
	- `setx ASPNETCORE_URLS "http://127.0.0.1:7000"` (one-time)
	- Close/reopen the terminal, then:
	- `dotnet run`

	If you don’t like env vars, just launch once like this instead:
	- `ASPNETCORE_URLS=http://127.0.0.1:7000 dotnet run`

2) Start the MITM proxy
- From the repo root: `python .\blue_archive_server_proxy.py`
- First run will pip-install what it needs.
- It listens on HTTP 9080 and HTTPS 9443.

3) Patch TLS in the client
- Run `ClientHook/inject.bat` (or `inject_v2.ps1` in an elevated PowerShell)

4) Flip to the private server
- Launch the game and get to the main menu
- Open: `http://127.0.0.1:9080/_proxy/flip`
- To revert: `http://127.0.0.1:9080/_proxy/unflip`
- Status: `http://127.0.0.1:9080/_proxy/status`

Notes
- Transparent redirect uses WinDivert and only kicks in after you flip. If you don’t run as Admin, it stays off. You can still test by setting a system proxy (HTTP 127.0.0.1:9080, HTTPS 127.0.0.1:9443) and removing it later.
- The proxy generates `certs/mitm_proxy_cert.pem`. With the TLS hook, you don’t need to trust it. If you insist on running without the hook, import that cert into “Trusted Root.”

## Ports
- API (private upstream): 7000
- Proxy HTTP control/data: 9080
- Proxy HTTPS MITM: 9443

Use at your own risk. Don’t point this at anything you don’t own.