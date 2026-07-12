# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## What this is

A mock **Aruba EdgeConnect SD-WAN Orchestrator REST API** (Flask) serving 18 SD-WAN
appliances across 6 Luminary Systems sites (Amsterdam, San Francisco, New York, London,
Singapore, Bangalore), so the **Infoblox Universal Asset Insights** Aruba EdgeConnect
connector can be pointed at a live HTTPS endpoint without a real Orchestrator instance.
Sibling project to mock-mist-api, mock-meraki-api, mock-crowdstrike-api, etc. Same
Flask-on-App-Runner pattern.

## Architecture

Single Flask app (`app.py`) loads JSON at startup:
- `seed_data/raw/appliances.json` — 18 SD-WAN appliance objects

Deployed via `Dockerfile` (gunicorn, port 8080).

## The API contract

Based on the Aruba EdgeConnect Orchestrator REST API (base path `/gms/rest/`):

| Method & path | Purpose |
|---|---|
| `POST /gms/rest/authentication/login` | Session login → `{token, ...}` |
| `GET /gms/rest/authentication/loginStatus` | Check auth |
| `GET /gms/rest/authentication/logout` | Logout |
| `GET /gms/rest/appliance` | All appliances or single via `?nePk=0.NE` |
| `GET /gms/rest/appliance/approved` | Approved appliances (richer schema) |
| `GET /gms/rest/appliance/networkRoleAndSite` | Hub/spoke role + site per appliance |
| `GET /gms/rest/appliancesSoftwareVersions` | Software version per appliance |
| `GET /gms/rest/appliance/extraInfo` | Suricata/signature version |
| `GET /gms/rest/interfaceState` | Per-appliance interface state via `?nePk=0.NE&cached=true` |
| `GET /gms/rest/group` | Orchestrator groups (stub) |
| `GET /` | Health check |
| `GET /debug/requests` | Last 50 request log |

**Auth:** UAI portal fields: **Username**, **Password**, **Orchestrator URL**.
UAI POSTs `{"user": "...", "password": "..."}` to `/gms/rest/authentication/login` and
uses the returned `X-Auth-Token` for subsequent calls. Permissive — any credentials accepted.
- Username: `lsys-ec-admin`
- Password: `Lum1nary@Aruba#2026`
- Orchestrator URL: `https://bbkvcuavhc.us-east-1.awsapprunner.com`
- Skip TLS Verification: **Enabled**
- IPAM Discovery: **Enabled**, Federated Realm: **Default**

## Key schema details

- **Primary key format:** `{index}.NE` (e.g., `0.NE`, `17.NE`)
- **IP field:** Both `IP` (uppercase) and `ip` (lowercase) are present (Orchestrator quirk)
- **hostname field:** `hostName` (camelCase with capital N)
- **networkRole:** `"1"` = hub, `"0"` = spoke (string, not int)
- **Hub sites:** Amsterdam, San Francisco (both have 6 appliances each; treated as SD-WAN hubs)
- **Spoke sites:** New York (2), London (1), Singapore (1), Bangalore (2)
- **Models:** `EC-S` (200 Mbps), `EC-SD-B` (100 Mbps)
- **softwareVersion:** `"9.3.1.0_95994"` (all appliances same version)

## Data generation

```bash
python3 seed_data/generate_ec_data.py
# reads assets_luminary.xlsx rows where category=sdwan and seen_by includes 'aruba'
# writes seed_data/raw/appliances.json
```

Central/local fallback:
```python
_CENTRAL = ROOT.parent / "luminary-demo-docs" / "master-sheet" / "assets_luminary.xlsx"
_LOCAL   = ROOT / "seed_data" / "source" / "assets_luminary.xlsx"
XLSX     = _CENTRAL if _CENTRAL.exists() else _LOCAL
```

`seed_data/raw/appliances.json` IS committed. xlsx files are gitignored.

## AWS / Docker deploy

ECR repo: `mock-aruba-ec-api` (account `905418046272`, region `us-east-1`).
Use intermediate tag to avoid zsh `:l` modifier bug:

```bash
docker build --no-cache --platform linux/amd64 -t mock-aruba-ec-build .
docker tag mock-aruba-ec-build 905418046272.dkr.ecr.us-east-1.amazonaws.com/mock-aruba-ec-api:latest
docker push 905418046272.dkr.ecr.us-east-1.amazonaws.com/mock-aruba-ec-api:latest
```

App Runner uses `AutoDeploymentsEnabled=True`. Service URL: `https://bbkvcuavhc.us-east-1.awsapprunner.com`
