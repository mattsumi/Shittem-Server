# Shittim-Server – Project Roadmap & Developer Guide

A local/private Blue Archive backend stack with a MITM redirector and an Admin GUI for live testing and account tooling.


# Note: This Server is currently not fully functional. I would greatly appriciate any and all help :) Please see issue #2 if you would like to help
---

## Vision

Match the official client’s expectations as closely as possible (JSON shape, protocol flow, and crypto) while providing local admin tooling to iterate quickly on gameplay features.

---

## Goals & Milestones

### Core Parity
- [ ] `/api/gateway` router: map protocol/opcode → handler
- [ ] Packet framing & crypto: encode/decode identical to client expectations
- [ ] Golden fixtures: captured request/response pairs to assert byte-for-byte parity

### Login & Session (baseline already working against official)
- [ ] `Queuing_GetTicketGL`
- [ ] `Account_CheckNexon`
- [ ] `Account_Auth` (seed/session issuance, server time, encrypted UID)

### Persistence
- [ ] Schema & migrations (Accounts, Currencies, Units/Roster, Inventory, Mail, Notices, GachaBanners/Pools/Drops, Missions, Purchases)
- [ ] Repository/services with transactions
- [ ] Seed data loader (banners, units, shop, missions)

### Gameplay Handlers (Minimum Set)
- **Gacha**
  - [ ] List banners (rates, pity info, schedule)
  - [ ] Draw (consume currency, dup/shard logic, pity updates)
  - [ ] Audit trail (history returned in official shape)
- **Units**
  - [ ] Level-up (validations, material consumption, updated roster block)
- **Shop**
  - [ ] List (daily/weekly/limited)
  - [ ] Purchase (price, stock, cooldown)
- **Missions**
  - [ ] List progress
  - [ ] Claim rewards (idempotent)

### Admin API (for the GUI)
- [ ] `POST /admin/mail` — send in-game mail (subject/body/attachments)
- [ ] `POST /admin/notice` — publish notice (title/text/schedule/priority)
- [ ] `GET /admin/account/{id}` — fetch account JSON
- [ ] `POST /admin/account/{id}` — patch account JSON (level, currencies, roster)
- [ ] `GET/POST /admin/gacha/banner` — create/update active banners & pools
- [ ] Local-only or token-guarded auth

### Admin GUI (PySide6)
- [ ] Mail tab — compose with attachments
- [ ] Notices tab — markdown/plain text, start/end, priority
- [ ] Account tab — fetch/edit raw JSON + quick fields (Level, Pyroxene, Credits)
- [ ] Server/MITM tab — start/stop mitmdump & C# API, flip/unflip, live logs
- [ ] Banner editor — configure featured units, rates, pity
- [ ] Roster editor — grant units, set levels/rarity, give items

### Observability & Quality
- [ ] Structured logs (redacted; request/response summaries)
- [ ] Error codes with remediation hints
- [ ] Protocol coverage dashboard (which handlers implemented/used)
- [ ] Golden tests (encode/decode + JSON schema validation)

---

## Repository Layout (expected)

```
/mitm/
  blue_archive_addon.py        # mitmproxy addon (flip/unflip, routing)
/server/                       # C# API project (dotnet)
  ...                          # controllers, services, persistence
/tools/
  seeds/                       # banner/pool/unit/shop seed data
ba_admin_gui.py                # PySide6 Admin GUI
README.md
```

> If paths differ, update them in the GUI “Server / MITM” tab or adjust the commands below.

---

## Getting Started

### Prereqs
- Python 3.11+ and `pip`
- PySide6: `pip install pyside6`
- mitmproxy 10+: `pip install mitmproxy`
- .NET SDK 7/8 (for the C# server)

### Run the Admin GUI
```bash
python ba_admin_gui.py
```

In **Server / MITM** tab:
1. (Optional) Set **C# API directory** to your `/server` project, click **Start C# API**.
2. Click **Start MITM**.  
3. Use **Flip Traffic** to route client `/api/gateway` calls to the private server.  
4. Use Mail/Notices/Account tabs to test admin endpoints.

---

## Acceptance Criteria (per feature)

### Admin Endpoints
- Return `200` with official-shaped JSON; validation passes.
- State persists across server restart.

### Gacha
- Draw results follow configured rates; pity increments/resets correctly.
- Currency deduction & unit/shard grants are consistent and atomic.
- Response mirrors official fields (names, casing, nesting, history/logs).

### Units
- Level-up enforces rules and consumption; roster block matches official response.

### Shop
- Lists reflect stock, cooldowns; purchases update stock and currencies.

### Missions
- Idempotent claims; rewards granted once; progress accurate.

---

## Implementation Plan (suggested order)

1. **Admin stubs** (return mock but official-shape JSON) → unblock GUI actions.
2. **DB migrations** for Accounts/Currencies/Units; wire `/admin/account` to persist.
3. **Gacha banner config** (read/write) → **Gacha_List**, then **Gacha_Draw** end-to-end.
4. **Mail/Notice** persistence & client fetch endpoints.
5. **Unit level-up** handler; then **Shop** and **Missions**.

---

## Testing

- **Golden fixtures**: store captured official request/response (after decryption) and assert:
  - decode(official_req) == server_req_model
  - encode(server_resp_model) == official_resp (byte-exact)
- **Schema checks**: JSON schema per endpoint, validated in CI.
- **Idempotency**: retry purchase/claim/draw flows under concurrency in tests.

---

## Troubleshooting

- **MITM stops immediately**  
  Verify `mitmdump` is on PATH and `blue_archive_addon.py` exists. Try launching from terminal to see import errors.

- **GUI “PermissionError: [WinError 5]” starting processes**  
  Run the GUI as admin or disable elevation; ensure `mitmdump.exe` and `dotnet` are accessible without elevation. Alternatively enable *Use shell (cmd.exe)* in settings and start via a `.bat`.

- **TLS handshake failed (livestream domains)**  
  The client may not trust the proxy CA for some hosts. This does not block `/api/gateway` flows.

- **GUI calls fail (connection refused)**  
  Ensure the C# API is running and the **Private API Base** matches its bind address (e.g., `http://127.0.0.1:7000`).

---

## Security & Ethics

This stack is for educational/testing purposes. Do not use it to disrupt, impersonate, or access third-party services without permission. Keep private endpoints bound to `localhost`, and protect any admin routes.

---

## Contributing

- Keep handlers small and pure; push side effects into services.
- Add/update golden fixtures when an official shape changes.
- Document new protocols and fields in code comments and schemas.
- Open PRs with clear “Before/After” and test coverage.

---

## Glossary

- **Flip/Unflip** — Toggle routing of specific domains from official to local private server.
- **Golden fixtures** — Canonical official request/response pairs used to assert parity.
- **Gateway** — The multiplexed `/api/gateway` endpoint carrying encrypted protocol messages.

---

## Status Snapshot (living checklist)

- [ ] Admin GUI (Mail/Notices/Account) fully wired to live endpoints  
- [ ] `/api/gateway` router + crypto verified  
- [ ] Gacha (list/draw) end-to-end  
- [ ] Units level-up  
- [ ] Shop list/purchase  
- [ ] Missions list/claim  
- [ ] Seeds + migrations + persistence  
- [ ] Golden tests + schema validation + coverage view

> Update this file as features land to keep scope visible and honest.
