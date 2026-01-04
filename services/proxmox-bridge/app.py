from flask import Flask, jsonify
from flask_cors import CORS
import requests
import urllib3
import os

urllib3.disable_warnings()

app = Flask(__name__)
CORS(app)

TOKEN_ID = os.environ.get("PROXMOX_TOKEN_ID")
TOKEN_SECRET = os.environ.get("PROXMOX_TOKEN_SECRET")

NODES = {
    "t560-proxmox": "https://192.168.3.169:8006",
    "r770-proxmox": "https://192.168.3.228:8006"
}

def get_headers():
    return {"Authorization": f"PVEAPIToken={TOKEN_ID}={TOKEN_SECRET}"}

@app.route("/health")
def health():
    return jsonify({"status": "ok", "nodes": list(NODES.keys())})

@app.route("/nodes")
def list_nodes():
    result = []
    for node_name, host in NODES.items():
        try:
            r = requests.get(f"{host}/api2/json/nodes/{node_name}/status", headers=get_headers(), verify=False, timeout=5)
            if r.ok:
                data = r.json()["data"]
                mem_used = data.get("memory", {}).get("used", 0)
                mem_total = data.get("memory", {}).get("total", 1)
                result.append({
                    "node": node_name,
                    "status": "online",
                    "cpu_percent": round(data.get("cpu", 0) * 100, 1),
                    "memory_percent": round(mem_used / max(mem_total, 1) * 100, 1),
                    "memory_total_gb": round(mem_total / (1024**3), 1),
                    "cpus": data.get("cpuinfo", {}).get("cpus", 0),
                    "uptime_hours": round(data.get("uptime", 0) / 3600, 1)
                })
        except Exception as e:
            result.append({"node": node_name, "status": "offline", "error": str(e)})
    return jsonify(result)

@app.route("/nodes/<node_name>/vms")
def list_vms(node_name):
    if node_name not in NODES:
        return jsonify({"error": "Node not found"}), 404
    try:
        r = requests.get(f"{NODES[node_name]}/api2/json/nodes/{node_name}/qemu", headers=get_headers(), verify=False, timeout=10)
        return jsonify(r.json().get("data", []))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/nodes/<node_name>/vms/<vmid>/<action>", methods=["POST"])
def vm_action(node_name, vmid, action):
    if node_name not in NODES:
        return jsonify({"error": "Node not found"}), 404
    if action not in ["start", "stop", "shutdown", "reboot"]:
        return jsonify({"error": "Invalid action"}), 400
    try:
        r = requests.post(f"{NODES[node_name]}/api2/json/nodes/{node_name}/qemu/{vmid}/status/{action}", headers=get_headers(), verify=False, timeout=10)
        return jsonify({"success": r.ok, "data": r.json()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/cluster/resources")
def cluster_resources():
    all_vms = []
    all_nodes = []
    for node_name, host in NODES.items():
        try:
            r = requests.get(f"{host}/api2/json/nodes/{node_name}/status", headers=get_headers(), verify=False, timeout=5)
            if r.ok:
                data = r.json()["data"]
                mem_used = data.get("memory", {}).get("used", 0)
                mem_total = data.get("memory", {}).get("total", 1)
                all_nodes.append({
                    "node": node_name,
                    "status": "online",
                    "cpu_percent": round(data.get("cpu", 0) * 100, 1),
                    "memory_percent": round(mem_used / max(mem_total, 1) * 100, 1),
                    "memory_total_gb": round(mem_total / (1024**3), 1),
                    "cpus": data.get("cpuinfo", {}).get("cpus", 0),
                    "uptime_hours": round(data.get("uptime", 0) / 3600, 1)
                })
            r2 = requests.get(f"{host}/api2/json/nodes/{node_name}/qemu", headers=get_headers(), verify=False, timeout=5)
            if r2.ok:
                for vm in r2.json().get("data", []):
                    vm["node"] = node_name
                    all_vms.append(vm)
        except Exception as e:
            all_nodes.append({"node": node_name, "status": "offline", "error": str(e)})
    return jsonify({
        "nodes": all_nodes,
        "vms": sorted(all_vms, key=lambda x: (x.get("node", ""), x.get("vmid", 0))),
        "summary": {
            "total_nodes": len(all_nodes),
            "online_nodes": len([n for n in all_nodes if n.get("status") == "online"]),
            "total_vms": len(all_vms),
            "running_vms": len([v for v in all_vms if v.get("status") == "running"])
        }
    })

@app.route("/dashboard")
def dashboard():
    html = """<!DOCTYPE html>
<html>
<head>
<title>DARWIN Cluster</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,sans-serif;background:#0d1117;color:#c9d1d9;padding:20px}
h1{color:#58a6ff;margin-bottom:20px}
h2{color:#8b949e;margin:20px 0 10px;font-size:14px;text-transform:uppercase}
.summary{display:flex;gap:20px;margin-bottom:20px}
.summary-card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:15px 20px}
.summary-card .value{font-size:32px;font-weight:bold;color:#58a6ff}
.summary-card .label{color:#8b949e;font-size:12px}
.nodes{display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:15px;margin-bottom:20px}
.node-card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:15px}
.node-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.node-name{font-weight:bold;font-size:16px}
.node-status{padding:2px 8px;border-radius:12px;font-size:12px}
.node-status.online{background:#238636}
.node-status.offline{background:#f85149}
.node-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.metric{text-align:center}
.metric .value{font-size:18px;font-weight:bold}
.metric .label{font-size:11px;color:#8b949e}
.vms{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:10px}
.vm-card{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:12px;display:flex;justify-content:space-between;align-items:center}
.vm-info{display:flex;align-items:center;gap:10px}
.vm-status{width:10px;height:10px;border-radius:50%}
.vm-status.running{background:#3fb950}
.vm-status.stopped{background:#f85149}
.vm-name{font-weight:500}
.vm-node{font-size:11px;color:#8b949e}
.vm-specs{font-size:12px;color:#8b949e}
.vm-actions button{background:#21262d;border:1px solid #30363d;color:#c9d1d9;padding:4px 10px;border-radius:4px;cursor:pointer;margin-left:5px;font-size:12px}
.vm-actions button:hover{background:#30363d}
.vm-actions button.start{border-color:#238636;color:#3fb950}
.vm-actions button.stop{border-color:#f85149;color:#f85149}
.refresh{background:#21262d;border:1px solid #30363d;color:#c9d1d9;padding:8px 16px;border-radius:6px;cursor:pointer}
</style>
</head>
<body>
<div style="display:flex;justify-content:space-between;align-items:center">
<h1>DARWIN Cluster</h1>
<button class="refresh" onclick="loadData()">Refresh</button>
</div>
<div class="summary" id="summary"></div>
<h2>Nodes</h2>
<div class="nodes" id="nodes"></div>
<h2>Virtual Machines</h2>
<div class="vms" id="vms"></div>
<script>
async function loadData(){
const res=await fetch('/api/proxmox/cluster/resources');
const data=await res.json();
document.getElementById('summary').innerHTML=
'<div class="summary-card"><div class="value">'+data.summary.online_nodes+'/'+data.summary.total_nodes+'</div><div class="label">Nodes Online</div></div>'+
'<div class="summary-card"><div class="value">'+data.summary.running_vms+'</div><div class="label">VMs Running</div></div>'+
'<div class="summary-card"><div class="value">'+data.summary.total_vms+'</div><div class="label">Total VMs</div></div>';
document.getElementById('nodes').innerHTML=data.nodes.map(function(n){
return '<div class="node-card '+n.status+'"><div class="node-header"><span class="node-name">'+n.node+'</span><span class="node-status '+n.status+'">'+n.status+'</span></div>'+
(n.status==='online'?'<div class="node-metrics"><div class="metric"><div class="value">'+n.cpu_percent+'%</div><div class="label">CPU</div></div><div class="metric"><div class="value">'+n.memory_percent+'%</div><div class="label">RAM</div></div><div class="metric"><div class="value">'+n.cpus+'</div><div class="label">vCPUs</div></div><div class="metric"><div class="value">'+n.uptime_hours+'h</div><div class="label">Uptime</div></div></div>':'<div style="color:#f85149">'+(n.error||'Unreachable')+'</div>')+'</div>';
}).join('');
document.getElementById('vms').innerHTML=data.vms.map(function(v){
var mem=Math.round((v.maxmem||0)/(1024*1024*1024));
return '<div class="vm-card"><div class="vm-info"><div class="vm-status '+v.status+'"></div><div><div class="vm-name">'+(v.name||'VM '+v.vmid)+'</div><div class="vm-node">'+v.node+' - VMID '+v.vmid+'</div></div></div><div style="display:flex;align-items:center;gap:15px"><div class="vm-specs">'+(v.cpus||'?')+' vCPU - '+mem+'GB</div><div class="vm-actions">'+(v.status==='stopped'?'<button class="start" onclick="vmAction(\\''+v.node+'\\',\\''+v.vmid+'\\',\\'start\\')">Start</button>':'')+(v.status==='running'?'<button class="stop" onclick="vmAction(\\''+v.node+'\\',\\''+v.vmid+'\\',\\'shutdown\\')">Stop</button>':'')+'</div></div></div>';
}).join('');
}
async function vmAction(node,vmid,action){
await fetch('/api/proxmox/nodes/'+node+'/vms/'+vmid+'/'+action,{method:'POST'});
setTimeout(loadData,2000);
}
loadData();
setInterval(loadData,30000);
</script>
</body>
</html>"""
    return html

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
