"""
Mock Aruba EdgeConnect Orchestrator REST API
Flask app serving SD-WAN appliance data for Infoblox UAI integration testing.
"""

import json
import os
import sys
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
    ua = request.headers.get("User-Agent", "")
    auth = (request.headers.get("X-Auth-Token", "")
            or request.headers.get("Authorization", ""))
    # Print to stderr so every request appears in CloudWatch
    print(f"[REQ] {request.method} {request.path} ua={ua!r} auth={auth[:20]!r} args={dict(request.args)}",
          file=sys.stderr, flush=True)
    entry = {
        "ts":     datetime.now(timezone.utc).isoformat(),
        "method": request.method,
        "path":   request.path,
        "args":   dict(request.args),
        "ua":     ua,
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
    raw = request.get_data(as_text=True)
    body = request.get_json(silent=True) or {}
    print(f"[LOGIN] raw_body={raw!r} content_type={request.content_type!r}",
          file=sys.stderr, flush=True)
    user = body.get("user") or body.get("username") or request.form.get("user", "")
    pwd  = body.get("password") or request.form.get("password", "")
    if not user:
        return jsonify({"error": "user required"}), 400
    # Accept any non-empty credentials
    token = f"mock-token-{user}-2026"
    _VALID_TOKENS.add(token)
    session["authenticated"] = True
    resp = jsonify({
        "X-Auth-Token": token,
        "token":        token,
        "sessionId":    token,
        "userId":       1,
        "userName":     user,
        "role":         "admin",
    })
    resp.headers["X-Auth-Token"] = token
    return resp

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

# ---------------------------------------------------------------------------
# Interface state (per-appliance) — what UAI calls for each nePk
# ---------------------------------------------------------------------------
_SCALARS = {
    "maxWanBandwidth": 1000000000, "defaultMaxWanBandwidth": 1000000000,
    "maxRxTargetBandwidth": 2000000, "maxTunnels": 2000, "maxIKETunnels": 4000,
    "minMtu": 700, "maxMtu": 9000, "maxRouteMaps": 10, "maxOptMaps": 10,
    "maxQoSMaps": 10, "maxNatMaps": 10, "maxRouteMapEntries": 2000,
    "maxOptMapEntries": 200, "maxQoSMapEntries": 200, "maxNatMapEntries": 300,
    "isPortalLicensed": True, "portalLicenseType": 2, "supportServerMode": True,
    "isLicenseRequired": False, "isDynamicLimits": True, "isDynamicInterface": True,
    "isModel4Port": True, "isModel10G": False, "isModelSingleDisk": True,
    "isModelPowerCycle": False, "num1GigPorts": 32, "num1GigFiberPorts": 0,
    "numMgmtPorts": 2, "num10GigPorts": 0, "isGMSCompatible": True,
    "maxAcls": 100, "maxAclEntries": 100, "maxUDAs": 200, "maxUDAEntries": 400,
    "maxVLANs": 511, "maxSubInterfaces": 511, "diskLayout": "",
    "vrrpCompatible": False, "supportsBridgeLoopTest": True,
    "supportsDiskSelfTest": True, "supportsBypass": False,
    "isNMInDisklessMode": True, "nmDiskSize": 70, "processorCount": 2,
    "memorySize": 4, "cacheDiskCount": 0, "spindleDiskCount": 1,
    "maxFlows": 128000, "maxRedFlows": 1024000, "maxBypassFlows": 1024000,
    "actualProcessorCount": 2, "actualMemorySize": 4, "actualNMDiskSize": 70,
    "isModelForReplication": False, "maxIpServiceEntries": 1000000,
    "maxSaasEntries": 256000, "maxOverlays": 7, "maxSegMapEntries": 2000,
    "maxDnsProxySegments": 4, "maxRoutemaps": 10, "maxOptmaps": 10,
    "maxQosmaps": 10, "maxNatmaps": 10, "maxAcmaps": 10, "maxPolicymaps": 70,
    "maxMapnamelen": 32, "maxRulesperacl": 100, "maxAclrulelen": 1024,
    "isIdsSupported": False, "maxBrNatRulesAny": 256, "maxExpressApps": 50,
    "maxLocalBreakoutPrimaryLinks": 32, "maxLocalBreakoutBackupLinks": 16,
    "maxInternetPolicies": 32, "fileUploadLimit": 1073741824, "poeInterfaces": [],
}

def _mac_to_link_local(mac: str) -> str:
    """Compute IPv6 link-local address from MAC via EUI-64."""
    p = [int(x, 16) for x in mac.split(":")]
    p[0] ^= 0x02  # flip universally administered bit
    eui = p[:3] + [0xff, 0xfe] + p[3:]
    groups = [f"{eui[i * 2]:02x}{eui[i * 2 + 1]:02x}" for i in range(4)]
    groups = [g.lstrip("0") or "0" for g in groups]
    return f"fe80::{':'.join(groups)}"

def _build_interface_state(idx: int, mgmt_ip: str) -> dict:
    lan_ip  = f"192.168.{170 + idx}.10"
    wan0_ip = f"10.100.{idx * 2}.2"
    wan0_gw = f"10.100.{idx * 2}.1"
    wan1_ip = f"10.100.{idx * 2 + 1}.2"
    wan1_gw = f"10.100.{idx * 2 + 1}.1"
    h       = f"{idx:02x}"

    active_ifs = [
        {"ifname": "mgmt0", "admin": True, "oper": True, "ipv4": mgmt_ip,
         "ipv4mask": 24, "ipv4dhcp": True, "ifSpeed": "auto",
         "speed": "1000Mb/s (auto)", "ifDuplex": "auto", "duplex": "full (auto)",
         "mtu": 1500, "mac": f"00:50:56:00:{h}:00", "wan-if": False,
         "lan-if": False, "harden": False, "label": "", "publicIp": "",
         "ifIndex": "3", "comboPortSupported": "RJ45", "comboPortConfig": 0, "supported": ""},
        {"ifname": "mgmt1", "admin": False, "oper": False, "ipv4": "169.254.0.1",
         "ipv4mask": 16, "ipv4dhcp": False, "ifSpeed": "auto",
         "speed": "1000Mb/s (auto)", "ifDuplex": "auto", "duplex": "full (auto)",
         "mtu": 1500, "mac": "Unassigned", "wan-if": False, "lan-if": False,
         "harden": False, "label": "", "publicIp": "", "ifIndex": "9",
         "comboPortSupported": "RJ45", "comboPortConfig": 0, "supported": ""},
        {"ifname": "lan0", "admin": True, "oper": True, "ipv4": lan_ip,
         "ipv4mask": 24, "ipv4dhcp": False, "ifSpeed": "auto",
         "speed": "25000Mb/s (auto)", "ifDuplex": "auto", "duplex": "full (auto)",
         "mtu": 1500, "mac": f"00:50:56:00:{h}:01", "wan-if": False,
         "lan-if": True, "label": "5", "publicIp": lan_ip, "ifIndex": "4",
         "comboPortSupported": "RJ45", "comboPortConfig": 0, "supported": "",
         "vrf": 0, "nexthop": "0.0.0.0"},
        {"ifname": "wan0", "admin": True, "oper": True, "ipv4": wan0_ip,
         "ipv4mask": 24, "ipv4dhcp": False, "ifSpeed": "auto",
         "speed": "25000Mb/s (auto)", "ifDuplex": "auto", "duplex": "full (auto)",
         "mtu": 1500, "mac": f"00:50:56:00:{h}:02", "wan-if": True,
         "lan-if": False, "label": "1", "publicIp": wan0_ip, "ifIndex": "5",
         "comboPortSupported": "RJ45", "comboPortConfig": 0, "supported": "",
         "vrf": 0, "nexthop": wan0_gw},
        {"ifname": "wan1", "admin": True, "oper": True, "ipv4": wan1_ip,
         "ipv4mask": 24, "ipv4dhcp": False, "ifSpeed": "auto",
         "speed": "25000Mb/s (auto)", "ifDuplex": "auto", "duplex": "full (auto)",
         "mtu": 1500, "mac": f"00:50:56:00:{h}:03", "wan-if": True,
         "lan-if": False, "label": "2", "publicIp": wan1_ip, "ifIndex": "2",
         "comboPortSupported": "RJ45", "comboPortConfig": 0, "supported": "",
         "vrf": 0, "nexthop": wan1_gw},
    ]
    unassigned_lan = [
        {"ifname": f"lan{i}", "admin": True, "oper": True, "ipv4": "",
         "ipv4mask": "", "ipv4dhcp": False, "ifSpeed": "auto",
         "speed": "1000Mb/s (auto)", "ifDuplex": "auto", "duplex": "full (auto)",
         "mtu": 1500, "mac": "Unassigned", "wan-if": False, "lan-if": False,
         "harden": False, "label": "", "publicIp": "", "ifIndex": str(10 + i),
         "comboPortSupported": "RJ45", "comboPortConfig": 0, "supported": ""}
        for i in range(1, 16)
    ]
    unassigned_wan = [
        {"ifname": f"wan{i}", "admin": True, "oper": True, "ipv4": "",
         "ipv4mask": "", "ipv4dhcp": False, "ifSpeed": "auto",
         "speed": "1000Mb/s (auto)", "ifDuplex": "auto", "duplex": "full (auto)",
         "mtu": 1500, "mac": "Unassigned", "wan-if": False, "lan-if": False,
         "harden": False, "label": "", "publicIp": "", "ifIndex": str(27 + i),
         "comboPortSupported": "RJ45", "comboPortConfig": 0, "supported": ""}
        for i in range(2, 16)
    ]
    l3info = [
        {"name": "lan0", "type": 2, "ip": lan_ip, "mask": 24, "gw": "0.0.0.0",
         "gwState": 0, "numTunEndpoints": 1, "inMaxBw": 0, "outMaxBw": 0,
         "inTargetThres": 95, "outTargetThres": 95, "shaperIdx": 3,
         "lanOnly": True, "wanOnly": False, "dhcp": False, "p2p": False,
         "cell": False, "ha_if": False, "incomplete": False, "label": "5",
         "labelID": 2, "vrf_id": 0, "kernalVrfName": "default",
         "zone_id": 0, "valid": 1, "active": 1, "securityMode": 0},
        {"name": "wan0", "type": 2, "ip": wan0_ip, "mask": 24, "gw": wan0_gw,
         "gwState": 2, "numTunEndpoints": 8, "inMaxBw": 100000, "outMaxBw": 100000,
         "inTargetThres": 95, "outTargetThres": 95, "shaperIdx": 19,
         "lanOnly": False, "wanOnly": True, "dhcp": False, "p2p": False,
         "cell": False, "ha_if": False, "incomplete": False, "label": "1",
         "labelID": 3, "vrf_id": 0, "kernalVrfName": "default",
         "zone_id": 0, "valid": 1, "active": 1, "securityMode": 0},
        {"name": "wan1", "type": 2, "ip": wan1_ip, "mask": 24, "gw": wan1_gw,
         "gwState": 2, "numTunEndpoints": 8, "inMaxBw": 100000, "outMaxBw": 100000,
         "inTargetThres": 95, "outTargetThres": 95, "shaperIdx": 20,
         "lanOnly": False, "wanOnly": True, "dhcp": False, "p2p": False,
         "cell": False, "ha_if": False, "incomplete": False, "label": "2",
         "labelID": 4, "vrf_id": 0, "kernalVrfName": "default",
         "zone_id": 1, "valid": 1, "active": 1, "securityMode": 3},
    ]
    mac_ifs = (["mgmt0", "mgmt1"]
               + [f"lan{i}" for i in range(16)]
               + [f"wan{i}" for i in range(16)])
    addrstIp6 = {}
    for iface in active_ifs:
        mac = iface.get("mac", "")
        if mac and mac != "Unassigned":
            ipv6 = _mac_to_link_local(mac)
            addrstIp6[ipv6] = {
                "self": ipv6, "address": ipv6,
                "ifdevname": "", "ifname": iface["ifname"], "mask": 64,
            }
    return {
        "sysConfig": {"mode": "router", "submode": "inline", "bonding": False},
        "scalars": _SCALARS,
        "ifInfo": active_ifs + unassigned_lan + unassigned_wan,
        "addrstIp6": addrstIp6,
        "l3info": l3info,
        "macIfs": mac_ifs,
        "availMACs": [],
    }

@app.get("/gms/rest/interfaceState")
def get_interface_state():
    if not _check_auth():
        return _auth_error()
    ne_pk = request.args.get("nePk", "")
    if ne_pk not in _BY_NEPK:
        return jsonify({"error": f"Appliance {ne_pk} not found"}), 404
    a = _BY_NEPK[ne_pk]
    try:
        idx = int(ne_pk.split(".")[0])
    except (ValueError, IndexError):
        idx = 0
    mgmt_ip = a.get("ip") or a.get("IP") or "10.0.0.2"
    return jsonify(_build_interface_state(idx, mgmt_ip))

@app.errorhandler(404)
def not_found(e):
    print(f"[404] {request.method} {request.path} ua={request.headers.get('User-Agent','')!r}",
          file=sys.stderr, flush=True)
    return jsonify({"error": "not found", "path": request.path}), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
