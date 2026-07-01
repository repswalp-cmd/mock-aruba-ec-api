# Mock Aruba EdgeConnect Orchestrator API

A mock implementation of the **Aruba EdgeConnect SD-WAN Orchestrator REST API**,
designed for **Infoblox Universal Asset Insights** integration testing and demos.
Points the Infoblox Aruba EdgeConnect connector at a live HTTPS endpoint without a
real Orchestrator instance.

## Overview

Aruba EdgeConnect is an SD-WAN platform. The Orchestrator is the central management
plane; it exposes a REST API (base path `/gms/rest/`) that UAI queries for appliance inventory.

This mock serves **18 SD-WAN appliances** across 6 Luminary Systems sites drawn from
the Luminary Systems UAI Demo Dataset v7.

## API surface

| Method & path | Purpose |
|---|---|
| `POST /gms/rest/authentication/login` | Login — returns `X-Auth-Token` |
| `GET /gms/rest/authentication/loginStatus` | Check session |
| `GET /gms/rest/authentication/logout` | Invalidate session |
| `GET /gms/rest/appliance` | All appliances or single via `?nePk=` |
| `GET /gms/rest/appliance/approved` | Approved appliances with discovery metadata |
| `GET /gms/rest/appliance/networkRoleAndSite` | Hub/spoke roles per appliance |
| `GET /gms/rest/appliancesSoftwareVersions` | ECOS version info |
| `GET /gms/rest/appliance/extraInfo` | Suricata/signature version |
| `GET /gms/rest/group` | Orchestrator group hierarchy |

Extras: `GET /` health check, `GET /debug/requests` (request log).

### Authentication

The Orchestrator uses session-based auth. Login returns a token; pass it as
`X-Auth-Token` header or use the session cookie.

```bash
# Login
curl -X POST "$BASE/gms/rest/authentication/login" \
  -H "Content-Type: application/json" \
  -d '{"user":"admin","password":"admin123"}'

# Use token
curl -H "X-Auth-Token: <token>" "$BASE/gms/rest/appliance"
```

The mock is **permissive by default** — any username/password pair is accepted.
In the UAI portal, configure the connector with credential type **Username + Password**
and set the Base URL to the App Runner URL. Use `admin` / `admin123` as credentials.

## Data

**18 SD-WAN appliances** across 6 sites.

### Site breakdown

| Site | Appliances | Network Role |
|------|-----------|--------------|
| Amsterdam | 6 | Hub |
| San Francisco | 6 | Hub |
| New York | 2 | Spoke |
| Bangalore | 2 | Spoke |
| London | 1 | Spoke |
| Singapore | 1 | Spoke |
| **Total** | **18** | |

### Fleet breakdown

| Model | Count | Bandwidth |
|-------|-------|-----------|
| EdgeConnect EC-S | 9 | 200 Mbps |
| EdgeConnect SD-Branch | 9 | 100 Mbps |

### Key schema notes

- Primary key: `{index}.NE` format (e.g., `0.NE` through `17.NE`)
- Both `IP` (uppercase) and `ip` (lowercase) fields present on each appliance
- `hostName` uses camelCase with capital N
- `networkRole`: `"1"` = hub, `"0"` = spoke

### Cross-system matching

Hostnames / IPs / serial numbers come verbatim from the master sheet — Asset Insights
correlates the same physical device across Aruba EdgeConnect, ServiceNow, and other connectors.

Source of truth: [`luminary-demo-docs/master-sheet/assets_luminary.xlsx`](https://github.com/repswalp-cmd/luminary-demo-docs)
(Luminary Systems UAI Demo Dataset v7, ~2,295 total assets).

Regenerate deterministically:

```bash
python seed_data/generate_ec_data.py
# writes seed_data/raw/appliances.json
```

## Run locally

```bash
pip install -r requirements.txt
python app.py                 # serves on :5000
# or:
gunicorn app:app --bind 0.0.0.0:8080
```

## Deploy (AWS App Runner)

```bash
# Authenticate
aws sso login --profile okta-sso
aws ecr get-login-password --profile okta-sso --region us-east-1 \
  | docker login --username AWS --password-stdin \
    905418046272.dkr.ecr.us-east-1.amazonaws.com

# Build AMD64 (intermediate tag avoids zsh :l bug)
docker build --no-cache --platform linux/amd64 -t mock-aruba-ec-build .
docker tag mock-aruba-ec-build 905418046272.dkr.ecr.us-east-1.amazonaws.com/mock-aruba-ec-api:latest
docker push 905418046272.dkr.ecr.us-east-1.amazonaws.com/mock-aruba-ec-api:latest
```

App Runner picks up the new image automatically (`AutoDeploymentsEnabled=True`).

## Reference

`docs/ec_responses/` holds representative request/response pairs.

## Contact

Built for Infoblox Universal Asset Insights testing.
Contact: **TME — Rajkumar Repswal**

---
*Mock API for testing purposes. Not affiliated with or endorsed by Aruba Networks / HPE.*
