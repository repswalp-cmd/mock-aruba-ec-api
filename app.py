"""
Mock Aruba EdgeConnect Orchestrator REST API
Flask app serving SD-WAN appliance data for Infoblox UAI integration testing.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request, session

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "mock-aruba-ec-secret-key-2026")

# ---------------------------------------------------------------------------
# Load seed data
# ---------------------------------------------------------------------------
RAW = Path(__file__).parent / "seed_data" / "raw"

def _load(fname: str):
    p = RAW / fname
    if p.exists():
        return json.loads(p.read_text())
    return []

APPLIANCES: list[dict] = _load("appliances.json")
_BY_NEPK: dict[str, dict] = {a["nePk"]: a for a in APPLIANCES}

# ---------------------------------------------------------------------------
# Request log (debug)
# ---------------------------------------------------------------------------
_REQUEST_LOG: list[dict] = []
MAX_LOG = 200

@app.before_request
def _log_request():
    if request.path.startswith("/debug/"):
        return
    entry = {
        "ts":     datetime.now(timezone.utc).isoformat(),
        "method": request.method,
        "path":   request.path,
        "args":   dict(request.args),
        "headers": {k: v for k, v in request.headers if k in (
            "Authorization", "X-Auth-Token", "Content-Type",
        )},
    }
    _REQUEST_LOG.append(entry)
    if len(_REQUEST_LOG) > MAX_LOG:
        _REQUEST_LOG.pop(0)

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
REQUIRED_TOKEN = os.environ.get("ARUBA_EC_TOKEN", "")

_VALID_TOKENS: set[str] = set()

def _check_auth() -> bool:
    if not REQUIRED_TOKEN:
        return True  # permissive mode
    token = request.headers.get("X-Auth-Token", "")
    if token and token in _VALID_TOKENS:
        return True
    if session.get("authenticated"):
        return True
    return False

def _auth_error():
    return jsonify({"error": "Unauthorized — POST /gms/rest/authentication/login first"}), 401

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/")
def health():
    return jsonify({
        "status":     "ok",
        "service":    "mock-aruba-edgeconnect-orchestrator",
        "appliances": len(APPLIANCES),
        "version":    "9.3.1.0_95994",
    })

@app.get("/debug/requests")
def debug_requests():
    return jsonify(_REQUEST_LOG[-50:])

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
@app.post("/gms/rest/authentication/login")
def login():
    body = request.get_json(silent=True) or {}
    user = body.get("user") or body.get("username") or request.form.get("user", "")
    pwd  = body.get("password") or request.form.get("password", "")
    if not user:
        return jsonify({"error": "user required"}), 400
    # Accept any non-empty credentials
    token = f"mock-token-{user}-2026"
    _VALID_TOKENS.add(token)
    session["authenticated"] = True
    return jsonify({
        "token":    token,
        "expiry":   "2026-07-01T23:59:59Z",
        "role":     "admin",
        "userId":   1,
        "userName": user,
    })

@app.get("/gms/rest/authentication/loginStatus")
def login_status():
    return jsonify({
        "authenticated": _check_auth(),
        "userId":        1,
        "userName":      "admin",
    })

@app.get("/gms/rest/authentication/logout")
@app.post("/gms/rest/authentication/logout")
def logout():
    token = request.headers.get("X-Auth-Token", "")
    _VALID_TOKENS.discard(token)
    session.pop("authenticated", None)
    return jsonify({"status": "logged out"})

# ---------------------------------------------------------------------------
# Appliance inventory
# ---------------------------------------------------------------------------
@app.get("/gms/rest/appliance")
def get_appliances():
    if not _check_auth():
        return _auth_error()

    ne_pk = request.args.get("nePk")
    if ne_pk:
        if ne_pk in _BY_NEPK:
            return jsonify(_BY_NEPK[ne_pk])
        return jsonify({"error": f"Appliance {ne_pk} not found"}), 404

    return jsonify(APPLIANCES)

@app.get("/gms/rest/appliance/approved")
def get_approved_appliances():
    if not _check_auth():
        return _auth_error()
    approved = []
    for idx, a in enumerate(APPLIANCES):
        approved.append({
            "id":             a["nePk"],
            "uuid":           a["uuid"],
            "dynamicUuid":    a["dynamicUuid"],
            "portalObjectId": a["portalObjectId"],
            "approved":       True,
            "denied":         False,
            "approvedTime":   1751328000 + idx * 100,
            "deniedTime":     None,
            "discoveredTime": 1751000000 + idx * 100,
            "discoveredFrom": a["discoveredFrom"],
            "userId":         1,
            "applianceInfo": {
                "hostname":          a["hostName"],
                "model":             a["model"],
                "serial":            a["serial"],
                "softwareVersion":   a["softwareVersion"],
                "site":              a["site"],
                "ip":                a["ip"],
                "publicIp":          a["ip"],
                "reachabilityStatus":"reachable",
                "deviceType":        "APPLIANCE",
            },
        })
    return jsonify(approved)

@app.get("/gms/rest/appliance/networkRoleAndSite")
def get_network_role_and_site():
    if not _check_auth():
        return _auth_error()
    result = {}
    for a in APPLIANCES:
        result[a["nePk"]] = {
            "networkRole": int(a["networkRole"]),
            "site":        a["site"],
            "sitePriority": a["sitePriority"],
        }
    return jsonify(result)

# ---------------------------------------------------------------------------
# Software versions
# ---------------------------------------------------------------------------
@app.get("/gms/rest/appliancesSoftwareVersions")
def get_software_versions():
    if not _check_auth():
        return _auth_error()
    result = {}
    for a in APPLIANCES:
        result[a["nePk"]] = {
            "softwareVersion": a["softwareVersion"],
            "model":           a["model"],
            "platform":        a["platform"],
        }
    return jsonify(result)

# ---------------------------------------------------------------------------
# Summary / extra info (stubs that UAI may call)
# ---------------------------------------------------------------------------
@app.get("/gms/rest/appliance/extraInfo")
def get_extra_info():
    if not _check_auth():
        return _auth_error()
    ne_pk = request.args.get("nePk")
    appliances = [_BY_NEPK[ne_pk]] if ne_pk and ne_pk in _BY_NEPK else APPLIANCES
    result = {a["nePk"]: {"suricataVersion": a["suricataVersion"],
                          "signatureFamily":  a["signatureFamily"]}
              for a in appliances}
    return jsonify(result)

# ---------------------------------------------------------------------------
# Groups (stub — UAI may enumerate groups)
# ---------------------------------------------------------------------------
@app.get("/gms/rest/group")
def get_groups():
    if not _check_auth():
        return _auth_error()
    return jsonify([
        {"id": "1.Network", "name": "All EC Appliances", "parentId": None},
        {"id": "2.Network", "name": "Luminary Systems SD-WAN", "parentId": "1.Network"},
    ])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
