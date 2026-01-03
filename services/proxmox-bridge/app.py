from flask import Flask, jsonify, request, render_template_string
import requests
import urllib3
import os

urllib3.disable_warnings()

app = Flask(__name__)

PROXMOX = os.environ.get("PROXMOX_HOST", "https://proxmox:8006")
TOKEN_ID = os.environ.get("PROXMOX_TOKEN_ID", "root@pam!dashboard")
TOKEN_SECRET = os.environ.get("PROXMOX_TOKEN_SECRET", "")
NODE = os.environ.get("PROXMOX_NODE", "pve")

HEADERS = {"Authorization": f"PVEAPIToken={TOKEN_ID}={TOKEN_SECRET}"}

PROJECT_VMS = {
    "cockpit": {"vmid": 100, "name": "Cockpit", "icon": "terminal"},
    "pbpk": {"vmid": 101, "name": "PBPK", "icon": "pills"},
    "scaffold": {"vmid": 102, "name": "Scaffold Studio", "icon": "cubes"},
    "atlas": {"vmid": 103, "name": "Atlas", "icon": "brain"},
    "genomics": {"vmid": 104, "name": "Genomics", "icon": "dna"},
    "sounio": {"vmid": 105, "name": "Sounio", "icon": "code"},
    "ai-gpu": {"vmid": 110, "name": "AI GPU", "icon": "robot"},
}

def px_get(endpoint):
    try:
        r = requests.get(f"{PROXMOX}{endpoint}", headers=HEADERS, verify=False, timeout=10)
        return r.json().get("data", {})
    except Exception as e:
        return {"error": str(e)}

def px_post(endpoint, data=None):
    try:
        r = requests.post(f"{PROXMOX}{endpoint}", headers=HEADERS, data=data, verify=False, timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/vms")
def list_vms():
    data = px_get(f"/api2/json/nodes/{NODE}/qemu")
    if isinstance(data, dict) and "error" in data:
        return jsonify(data), 500
    vms = []
    for vm in data:
        vmid = vm["vmid"]
        project = next((k for k, v in PROJECT_VMS.items() if v["vmid"] == vmid), None)
        vms.append({
            "vmid": vmid,
            "name": vm.get("name", "unknown"),
            "status": vm.get("status", "unknown"),
            "cpu_percent": round(vm.get("cpu", 0) * 100, 1),
            "mem_gb": round(vm.get("mem", 0) / 1e9, 1),
            "maxmem_gb": round(vm.get("maxmem", 0) / 1e9, 1),
            "uptime_hours": round(vm.get("uptime", 0) / 3600, 1),
            "project": project,
            "icon": PROJECT_VMS.get(project, {}).get("icon", "server")
        })
    return jsonify(sorted(vms, key=lambda x: x["vmid"]))

@app.route("/vm/<int:vmid>/start", methods=["POST"])
def start_vm(vmid):
    result = px_post(f"/api2/json/nodes/{NODE}/qemu/{vmid}/status/start")
    return jsonify({"success": "data" in result, "result": result})

@app.route("/vm/<int:vmid>/shutdown", methods=["POST"])
def shutdown_vm(vmid):
    result = px_post(f"/api2/json/nodes/{NODE}/qemu/{vmid}/status/shutdown")
    return jsonify({"success": "data" in result, "result": result})

@app.route("/vm/<int:vmid>/stop", methods=["POST"])
def stop_vm(vmid):
    result = px_post(f"/api2/json/nodes/{NODE}/qemu/{vmid}/status/stop")
    return jsonify({"success": "data" in result, "result": result})

@app.route("/node")
def node_status():
    data = px_get(f"/api2/json/nodes/{NODE}/status")
    if isinstance(data, dict) and "error" in data:
        return jsonify(data), 500
    return jsonify({
        "cpu_percent": round(data.get("cpu", 0) * 100, 1),
        "mem_used_gb": round(data.get("memory", {}).get("used", 0) / 1e9, 1),
        "mem_total_gb": round(data.get("memory", {}).get("total", 0) / 1e9, 1),
        "uptime_days": round(data.get("uptime", 0) / 86400, 1),
    })

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VM Control</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: system-ui, sans-serif; background: #0d1117; color: #c9d1d9; padding: 20px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
        .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }
        .card:hover { border-color: #58a6ff; }
        .card-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
        .card-icon { width: 40px; height: 40px; border-radius: 8px; display: flex; align-items: center; justify-content: center; }
        .card-icon.running { background: #238636; }
        .card-icon.stopped { background: #6e7681; }
        .card-title { font-weight: 600; }
        .card-subtitle { font-size: 12px; color: #8b949e; }
        .metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 12px 0; }
        .metric { background: #21262d; padding: 8px; border-radius: 4px; }
        .metric-label { font-size: 10px; color: #8b949e; text-transform: uppercase; }
        .metric-value { font-size: 14px; font-weight: 600; }
        .actions { display: flex; gap: 8px; }
        .btn { flex: 1; padding: 8px; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-start { background: #238636; color: white; }
        .btn-stop { background: #da3633; color: white; }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; }
        .status-dot.running { background: #3fb950; }
        .status-dot.stopped { background: #6e7681; }
    </style>
</head>
<body>
    <div class="grid" id="vm-grid"></div>
    <script>
        const ICONS = {terminal:'fa-terminal',pills:'fa-pills',cubes:'fa-cubes',brain:'fa-brain',dna:'fa-dna',code:'fa-code',robot:'fa-robot',server:'fa-server'};
        async function load() {
            const r = await fetch('/vms');
            const vms = await r.json();
            document.getElementById('vm-grid').innerHTML = vms.map(vm => `
                <div class="card">
                    <div class="card-header">
                        <div class="card-icon ${vm.status}"><i class="fas ${ICONS[vm.icon]||'fa-server'}"></i></div>
                        <div>
                            <div class="card-title">${vm.name}</div>
                            <div class="card-subtitle"><span class="status-dot ${vm.status}"></span>${vm.status} · VMID ${vm.vmid}</div>
                        </div>
                    </div>
                    <div class="metrics">
                        <div class="metric"><div class="metric-label">CPU</div><div class="metric-value">${vm.cpu_percent}%</div></div>
                        <div class="metric"><div class="metric-label">Memory</div><div class="metric-value">${vm.mem_gb}/${vm.maxmem_gb}GB</div></div>
                    </div>
                    <div class="actions">
                        <button class="btn btn-start" onclick="action(${vm.vmid},'start')" ${vm.status==='running'?'disabled':''}>Start</button>
                        <button class="btn btn-stop" onclick="action(${vm.vmid},'shutdown')" ${vm.status==='stopped'?'disabled':''}>Stop</button>
                    </div>
                </div>
            `).join('');
        }
        async function action(vmid, act) { await fetch(`/vm/${vmid}/${act}`, {method:'POST'}); setTimeout(load, 2000); }
        load(); setInterval(load, 30000);
    </script>
</body>
</html>
"""

@app.route("/dashboard")
def dashboard():
    return render_template_string(DASHBOARD_HTML)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
