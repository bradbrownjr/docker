#!/usr/bin/env python3
"""AI Stack Dashboard — python3 dashboard.py [--port 8888]"""

import http.server, json, subprocess, os, pathlib, socket, socketserver, sys
from urllib.parse import urlparse

PORT      = int(os.environ.get("DASHBOARD_PORT", "8888"))
HOST      = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
STACK_DIR = pathlib.Path(__file__).parent.resolve()
COMPOSE   = STACK_DIR / "docker-compose.yml"
ENV_FILE  = STACK_DIR / ".env"
CFG_FILE  = STACK_DIR / ".dashboard.json"

SERVICES = [
    dict(name="openwebui", label="OpenWebUI",   port=3000,  path="/",     color="#2563eb", icon="💬", profile=None,       buildable=False, desc="Main AI chat interface"),
    dict(name="ollama",    label="Ollama",       port=11434, path=None,    color="#f97316", icon="🦙", profile=None,       buildable=False, desc="LLM inference engine"),
    dict(name="comfyui",   label="ComfyUI",      port=8188,  path="/",     color="#7c3aed", icon="🎨", profile=None,       buildable=True,  desc="Image generation · Flux2-Klein"),
    dict(name="kokoro",    label="Kokoro TTS",   port=8880,  path="/docs", color="#db2777", icon="🔊", profile=None,       buildable=False, desc="Text-to-speech"),
    dict(name="speaches",  label="Speaches STT", port=9000,  path="/docs", color="#0d9488", icon="🎤", profile=None,       buildable=False, desc="Speech-to-text · Whisper"),
    dict(name="searxng",   label="SearXNG",      port=8080,  path="/",     color="#dc2626", icon="🔍", profile=None,       buildable=False, desc="Private web search"),
    dict(name="voicebox",  label="Voicebox",     port=17493, path="/",     color="#4f46e5", icon="🎙️", profile="voicebox", buildable=True,  desc="Voice cloning & studio"),
    dict(name="odysseus",  label="Odysseus",     port=7000,  path="/",     color="#d97706", icon="🚢", profile="odysseus", buildable=True,  desc="AI agent platform"),
    dict(name="chromadb",  label="ChromaDB",     port=8100,  path="/docs", color="#059669", icon="🗄️", profile="odysseus", buildable=False, desc="Vector database"),
    dict(name="ntfy",      label="ntfy",         port=8091,  path="/",     color="#0284c7", icon="🔔", profile="odysseus", buildable=False, desc="Push notifications"),
]

ENV_DEPS = {
    "HF_TOKEN":                ["comfyui","odysseus"],
    "LOW_VRAM":                ["comfyui"],
    "SEARXNG_SECRET":          ["searxng"],
    "ODYSSEUS_ADMIN_USER":     ["odysseus"],
    "ODYSSEUS_ADMIN_PASSWORD": ["odysseus"],
    "OPENAI_API_KEY":          ["odysseus"],
    "DATA_BRAVE_API_KEY":      ["odysseus"],
    "GOOGLE_API_KEY":          ["odysseus"],
    "GOOGLE_PSE_CX":           ["odysseus"],
    "TAVILY_API_KEY":          ["odysseus"],
    "SERPER_API_KEY":          ["odysseus"],
    "APP_BIND":                ["odysseus"],
    "APP_PORT":                ["odysseus"],
    "APP_DATA_DIR":            ["odysseus"],
    "APP_LOGS_DIR":            ["odysseus"],
    "CHROMADB_BIND":           ["chromadb"],
    "NTFY_BIND":               ["ntfy"],
    "NTFY_BASE_URL":           ["ntfy"],
    "PUID":                    ["odysseus"],
    "PGID":                    ["odysseus"],
}

# ── helpers ───────────────────────────────────────────────────────────────────

def load_cfg():
    try: return json.loads(CFG_FILE.read_text())
    except: return {"profiles": []}

def save_cfg(c): CFG_FILE.write_text(json.dumps(c, indent=2))

def active_profiles(): return load_cfg().get("profiles", [])

def compose_base(extra=()):
    profs = list(set(active_profiles()) | set(extra))
    cmd = ["docker","compose","-f",str(COMPOSE),"--env-file",str(ENV_FILE)]
    for p in profs: cmd += ["--profile", p]
    return cmd

def compose_run(args, extra=(), timeout=120):
    cmd = compose_base(extra) + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(STACK_DIR))
    return {"ok": r.returncode == 0, "out": r.stdout, "err": r.stderr}

def get_statuses():
    cmd = compose_base(["voicebox","odysseus"]) + ["ps","--format","json"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=10, cwd=str(STACK_DIR))
    by_name = {}
    if r.returncode == 0:
        for line in r.stdout.splitlines():
            try:
                c = json.loads(line)
                by_name[c["Service"]] = {"state": c.get("State",""), "status": c.get("Status","")}
            except: pass
    profs = active_profiles()
    return [{**s,
             "state": by_name.get(s["name"],{}).get("state","not_created"),
             "status_text": by_name.get(s["name"],{}).get("status","Not created"),
             "profile_active": s["profile"] is None or s["profile"] in profs}
            for s in SERVICES]

def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close(); return ip
    except: return "127.0.0.1"

# ── HTTP handler ──────────────────────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin","*")
        self.end_headers(); self.wfile.write(body)

    def body(self):
        n = int(self.headers.get("Content-Length",0))
        raw = self.rfile.read(n).decode() if n else ""
        try: return json.loads(raw)
        except: return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type")
        self.end_headers()

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/", "/index.html"):
            html = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length", len(html))
            self.end_headers(); self.wfile.write(html)
        elif p == "/api/status":
            self.send_json({"services": get_statuses(), "profiles": active_profiles(), "lan_ip": lan_ip()})
        elif p == "/api/env":
            self.send_json({"content": ENV_FILE.read_text() if ENV_FILE.exists() else "", "env_deps": ENV_DEPS})
        elif p == "/api/env/example":
            ex = STACK_DIR / ".env.example"
            self.send_json({"content": ex.read_text() if ex.exists() else ""})
        elif p.startswith("/api/logs/"):
            self._stream_logs(p[len("/api/logs/"):])
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        p = urlparse(self.path).path
        d = self.body()

        if p == "/api/env":
            ENV_FILE.write_text(d.get("content",""))
            self.send_json({"ok": True})
        elif p == "/api/config":
            cfg = load_cfg(); cfg.update(d); save_cfg(cfg)
            self.send_json({"ok": True})
        elif p.startswith("/api/service/"):
            parts = p[len("/api/service/"):].rsplit("/", 1)
            svc_name, action = parts[0], parts[1]
            svc = next((s for s in SERVICES if s["name"] == svc_name), None)
            extra = [svc["profile"]] if svc and svc["profile"] else []
            if action == "start":
                r = compose_run(["up","-d","--remove-orphans", svc_name], extra)
            elif action == "stop":
                r = compose_run(["stop", svc_name])
            elif action == "restart":
                r = compose_run(["restart", svc_name], extra)
            elif action == "pull":
                if svc and svc.get("buildable"):
                    compose_run(["build","--pull", svc_name], extra, timeout=600)
                else:
                    compose_run(["pull", svc_name], extra, timeout=300)
                r = compose_run(["up","-d","--force-recreate", svc_name], extra)
            else:
                self.send_response(404); self.end_headers(); return
            self.send_json(r)
        elif p == "/api/stack/start":
            self.send_json(compose_run(["up","-d","--remove-orphans"]))
        elif p == "/api/stack/stop":
            self.send_json(compose_run(["down"]))
        elif p == "/api/stack/restart":
            self.send_json(compose_run(["up","-d","--force-recreate","--remove-orphans"]))
        elif p == "/api/stack/pull":
            compose_run(["pull"], timeout=600)
            self.send_json(compose_run(["up","-d","--remove-orphans"]))
        else:
            self.send_response(404); self.end_headers()

    def _stream_logs(self, svc):
        self.send_response(200)
        self.send_header("Content-Type","text/event-stream")
        self.send_header("Cache-Control","no-cache")
        self.send_header("Connection","keep-alive")
        self.send_header("Access-Control-Allow-Origin","*")
        self.end_headers()
        cmd = compose_base(["voicebox","odysseus"]) + ["logs","--tail=200","-f", svc]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, cwd=str(STACK_DIR))
        try:
            for line in proc.stdout:
                self.wfile.write(f"data: {json.dumps(line.rstrip())}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError): pass
        finally: proc.terminate()

# ── HTML ──────────────────────────────────────────────────────────────────────

_SERVICES_JSON = json.dumps(SERVICES)

HTML = r"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Stack</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0c0c11;--surf:#15151d;--surf2:#1c1c27;--surf3:#22222f;
  --bdr:#2a2a3c;--txt:#dde4f0;--muted:#7a85a0;--dim:#454860;
  --acc:#6366f1;--acc2:#818cf8;--accbg:rgba(99,102,241,.14);
  --grn:#22c55e;--ylw:#f59e0b;--red:#ef4444;
  --r:12px;--rs:8px;--shadow:0 8px 32px rgba(0,0,0,.5);
  --tr:.18s ease;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
}
[data-theme=light]{
  --bg:#eef1f8;--surf:#fff;--surf2:#f4f6fb;--surf3:#eaedf5;
  --bdr:#dde3ee;--txt:#1a2035;--muted:#5a6680;--dim:#9aa5bd;
  --acc:#4f46e5;--acc2:#6366f1;--accbg:rgba(79,70,229,.09);
  --shadow:0 8px 32px rgba(0,0,0,.1);
}
body{background:var(--bg);color:var(--txt);min-height:100vh;display:grid;
  grid-template-columns:216px 1fr;grid-template-rows:54px 1fr}

/* header */
header{grid-column:1/-1;background:var(--surf);border-bottom:1px solid var(--bdr);
  display:flex;align-items:center;padding:0 18px;gap:14px;z-index:50;
  position:sticky;top:0}
.logo{display:flex;align-items:center;gap:9px;font-weight:800;font-size:1rem;
  letter-spacing:-.02em}
.logo-mark{width:30px;height:30px;border-radius:8px;font-size:17px;
  background:linear-gradient(135deg,#6366f1,#a855f7);
  display:flex;align-items:center;justify-content:center}
.hsp{flex:1}
.health{display:flex;align-items:center;gap:7px;padding:5px 13px;
  border-radius:20px;background:var(--surf2);border:1px solid var(--bdr);
  font-size:.78rem;font-weight:600}
.hdot{width:8px;height:8px;border-radius:50%;background:var(--dim)}
.hdot.up{background:var(--grn);box-shadow:0 0 8px var(--grn);animation:pulse 2.5s infinite}
.hdot.partial{background:var(--ylw)}
.hdot.down{background:var(--red)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.icon-btn{width:34px;height:34px;border-radius:7px;background:var(--surf2);
  border:1px solid var(--bdr);color:var(--muted);cursor:pointer;font-size:16px;
  display:flex;align-items:center;justify-content:center;transition:var(--tr)}
.icon-btn:hover{background:var(--surf3);color:var(--txt)}

/* sidebar */
nav{background:var(--surf);border-right:1px solid var(--bdr);
  padding:14px 10px;display:flex;flex-direction:column;gap:2px;overflow-y:auto}
.nl{font-size:.68rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
  color:var(--dim);padding:14px 10px 5px}
.nb{display:flex;align-items:center;gap:9px;padding:9px 10px;border-radius:var(--rs);
  border:none;background:none;color:var(--muted);cursor:pointer;font-size:.88rem;
  font-weight:500;transition:var(--tr);width:100%;text-align:left}
.nb:hover{background:var(--surf2);color:var(--txt)}
.nb.on{background:var(--accbg);color:var(--acc2)}
.nb .ni{font-size:17px;width:22px;text-align:center}

/* main */
main{padding:22px;overflow-y:auto;display:flex;flex-direction:column;gap:22px}
.view{display:none;flex-direction:column;gap:18px}
.view.on{display:flex}

/* stack bar */
.sbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.sbar-label{font-size:.76rem;font-weight:700;letter-spacing:.07em;
  text-transform:uppercase;color:var(--muted)}
.pills{display:flex;gap:7px;align-items:center}
.pill{display:flex;align-items:center;gap:5px;padding:4px 11px;
  border-radius:20px;border:1.5px solid var(--bdr);background:var(--surf2);
  font-size:.75rem;font-weight:700;cursor:pointer;transition:var(--tr);color:var(--muted)}
.pill.on{border-color:var(--acc);background:var(--accbg);color:var(--acc2)}
.pill-dot{width:5px;height:5px;border-radius:50%;background:currentColor}

/* buttons */
.btn{display:inline-flex;align-items:center;gap:5px;padding:7px 14px;
  border-radius:var(--rs);border:1px solid var(--bdr);background:var(--surf2);
  color:var(--txt);font-size:.82rem;font-weight:500;cursor:pointer;
  transition:var(--tr);white-space:nowrap;font-family:inherit}
.btn:hover{background:var(--surf3);border-color:var(--muted)}
.btn:active{transform:scale(.97)}
.btn.pri{background:var(--acc);border-color:var(--acc);color:#fff}
.btn.pri:hover{filter:brightness(1.12)}
.btn.dng{background:rgba(239,68,68,.1);border-color:rgba(239,68,68,.25);color:#f87171}
.btn.dng:hover{background:rgba(239,68,68,.18)}
.btn.sm{padding:5px 10px;font-size:.76rem}
.btn:disabled{opacity:.35;cursor:not-allowed;transform:none}

/* section */
.sec{display:flex;flex-direction:column;gap:10px}
.sec-hdr{display:flex;align-items:center;gap:10px}
.sec-title{font-size:.74rem;font-weight:700;letter-spacing:.07em;
  text-transform:uppercase;color:var(--muted);white-space:nowrap}
.sec-line{flex:1;height:1px;background:var(--bdr)}

/* grid */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:14px}

/* card */
.card{background:var(--surf);border:1px solid var(--bdr);border-radius:var(--r);
  overflow:hidden;transition:border-color var(--tr),box-shadow var(--tr)}
.card:hover{border-color:var(--muted);box-shadow:var(--shadow)}
.card.dim{opacity:.45}
.ca{height:3px}
.cb{padding:15px}
.ch{display:flex;align-items:flex-start;gap:11px;margin-bottom:13px}
.ci{width:42px;height:42px;border-radius:9px;display:flex;align-items:center;
  justify-content:center;font-size:21px;flex-shrink:0}
.cm{flex:1;min-width:0}
.cn{font-weight:700;font-size:.93rem}
.cd{font-size:.75rem;color:var(--muted);margin-top:2px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cp{font-size:.69rem;color:var(--dim);margin-top:3px;font-family:monospace}
.stag{display:inline-block;font-size:.62rem;font-weight:700;letter-spacing:.05em;
  text-transform:uppercase;padding:2px 7px;border-radius:4px;
  background:var(--surf3);color:var(--dim);border:1px solid var(--bdr);margin-bottom:7px}

/* status badge */
.sbadge{display:inline-flex;align-items:center;gap:4px;padding:3px 8px;
  border-radius:20px;font-size:.7rem;font-weight:700;flex-shrink:0}
.sbadge.running{background:rgba(34,197,94,.13);color:#4ade80}
.sbadge.exited,.sbadge.stopped{background:rgba(239,68,68,.1);color:#f87171}
.sbadge.restarting,.sbadge.starting{background:rgba(245,158,11,.13);color:#fbbf24}
.sbadge.not_created,.sbadge.created{background:rgba(100,116,139,.1);color:#94a3b8}
.sdot{width:5px;height:5px;border-radius:50%;background:currentColor}

/* card actions */
.cact{display:flex;gap:5px;flex-wrap:wrap;align-items:center}
.open-btn{margin-left:auto}

/* env editor */
.ewrap{background:var(--surf);border:1px solid var(--bdr);border-radius:var(--r);overflow:hidden}
.etbar{display:flex;align-items:center;gap:10px;padding:11px 15px;
  border-bottom:1px solid var(--bdr);background:var(--surf2)}
.etitle{font-size:.85rem;font-weight:700}
.eta{width:100%;min-height:420px;background:var(--surf);color:var(--txt);
  border:none;outline:none;resize:vertical;
  font-family:'SF Mono','Fira Code','Cascadia Code',monospace;
  font-size:.82rem;line-height:1.75;padding:16px;tab-size:2}
.rbanner{display:none;align-items:flex-start;gap:11px;padding:13px 15px;
  background:rgba(245,158,11,.08);border-top:1px solid rgba(245,158,11,.25);
  color:#fbbf24;font-size:.8rem}
.rbanner.on{display:flex}
.rbi{font-size:16px;flex-shrink:0;margin-top:1px}
.rbc{flex:1}
.rbl{margin-top:7px;display:flex;flex-wrap:wrap;gap:6px}
.rchip{padding:2px 9px;border-radius:4px;background:rgba(245,158,11,.12);
  border:1px solid rgba(245,158,11,.25);font-size:.72rem;font-weight:700}

/* logs */
.lctrl{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.lsel{padding:7px 12px;border-radius:var(--rs);border:1px solid var(--bdr);
  background:var(--surf);color:var(--txt);font-size:.83rem;cursor:pointer;
  outline:none;min-width:170px;font-family:inherit}
.lout{background:#08080d;border:1px solid var(--bdr);border-radius:var(--r);
  font-family:'SF Mono','Fira Code',monospace;font-size:.76rem;line-height:1.65;
  color:#8899bb;padding:14px;height:520px;overflow-y:auto;
  white-space:pre-wrap;word-break:break-all}
[data-theme=light] .lout{background:#12162a;color:#8899bb}
.ll-err{color:#fc8181}.ll-warn{color:#fbbf24}.ll-ok{color:#6ee7b7}.ll-dim{color:#4a5568}

/* toasts */
#tc{position:fixed;bottom:20px;right:20px;display:flex;flex-direction:column;
  gap:8px;z-index:9999}
.toast{padding:11px 16px;border-radius:var(--rs);background:var(--surf);
  border:1px solid var(--bdr);box-shadow:var(--shadow);font-size:.82rem;
  font-weight:500;display:flex;align-items:center;gap:9px;max-width:300px;
  animation:tin .18s ease}
.toast.ok{border-left:3px solid var(--grn)}
.toast.err{border-left:3px solid var(--red)}
.toast.inf{border-left:3px solid var(--acc)}
@keyframes tin{from{transform:translateX(16px);opacity:0}to{transform:none;opacity:1}}

/* spinner */
@keyframes spin{to{transform:rotate(360deg)}}
.spin{width:13px;height:13px;border:2px solid currentColor;
  border-top-color:transparent;border-radius:50%;
  animation:spin .55s linear infinite;display:inline-block}

@media(max-width:700px){
  body{grid-template-columns:1fr;grid-template-rows:54px auto 1fr}
  nav{flex-direction:row;border-right:none;border-bottom:1px solid var(--bdr);
    overflow-x:auto;padding:6px}
  .nl{display:none}
  .grid{grid-template-columns:1fr}
}
</style>
</head>
<body>

<header>
  <div class="logo">
    <div class="logo-mark">🤖</div>
    <span>AI Stack</span>
  </div>
  <div class="hsp"></div>
  <div class="health"><div class="hdot" id="hdot"></div><span id="htxt">Loading…</span></div>
  <button class="icon-btn" id="tbtn" title="Toggle theme">🌙</button>
</header>

<nav>
  <div class="nl">Navigate</div>
  <button class="nb on" data-view="dashboard"><span class="ni">📊</span>Dashboard</button>
  <button class="nb" data-view="env"><span class="ni">⚙️</span>.env Editor</button>
  <button class="nb" data-view="logs"><span class="ni">📋</span>Logs</button>
</nav>

<main>

  <!-- Dashboard -->
  <div class="view on" id="view-dashboard">
    <div class="sbar">
      <span class="sbar-label">Stack</span>
      <div class="pills" id="pills"></div>
      <button class="btn sm pri" onclick="stackAct('start')">▶ Start All</button>
      <button class="btn sm" onclick="stackAct('restart')">↺ Restart All</button>
      <button class="btn sm dng" onclick="stackAct('stop')">■ Stop All</button>
      <button class="btn sm" onclick="stackAct('pull')" title="Pull latest images">⬇ Update</button>
    </div>
    <div id="svc-container"></div>
  </div>

  <!-- .env Editor -->
  <div class="view" id="view-env">
    <div class="ewrap">
      <div class="etbar">
        <span class="etitle">📄 .env</span>
        <span style="flex:1;font-size:.75rem;color:var(--muted)">Edit and save — affected services are shown below</span>
        <button class="btn sm" onclick="loadExample()">↩ Reset to example</button>
        <button class="btn sm pri" onclick="saveEnv()">💾 Save</button>
      </div>
      <textarea class="eta" id="eta" spellcheck="false"></textarea>
      <div class="rbanner" id="rbanner">
        <span class="rbi">⚠️</span>
        <div class="rbc">
          <strong>Restart required</strong> — these services use changed variables:
          <div class="rbl" id="rbl"></div>
        </div>
      </div>
    </div>
  </div>

  <!-- Logs -->
  <div class="view" id="view-logs">
    <div class="lctrl">
      <select class="lsel" id="lsel" onchange="startLogs()">
        <option value="">— select service —</option>
      </select>
      <button class="btn sm" onclick="clearLog()">🗑 Clear</button>
      <button class="btn sm" id="lfbtn" onclick="toggleFollow()">📌 Following</button>
    </div>
    <div class="lout" id="lout">Select a service above to tail its logs.</div>
  </div>

</main>
<div id="tc"></div>

<script>
const SVC_META = """ + _SERVICES_JSON + r""";

const S = {
  svcs: [], profiles: [], lanIp: '127.0.0.1',
  theme: localStorage.getItem('theme') || 'dark',
  logEs: null, logFollow: true,
  envOrig: '', envDeps: {},
  pending: new Set(),
};

// ── boot ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  applyTheme(S.theme);
  loadStatus();
  loadEnv();
  populateLogSel();
  setInterval(loadStatus, 4000);
  document.querySelectorAll('.nb[data-view]').forEach(b =>
    b.addEventListener('click', () => nav(b.dataset.view)));
  document.getElementById('eta').addEventListener('input', onEnvChange);
});

// ── theme ─────────────────────────────────────────────────────────────────────
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  document.getElementById('tbtn').textContent = t === 'dark' ? '☀️' : '🌙';
  localStorage.setItem('theme', t);
  S.theme = t;
}
document.getElementById('tbtn').addEventListener('click', () =>
  applyTheme(S.theme === 'dark' ? 'light' : 'dark'));

// ── navigation ────────────────────────────────────────────────────────────────
function nav(v) {
  document.querySelectorAll('.view').forEach(el => el.classList.remove('on'));
  document.querySelectorAll('.nb').forEach(b => b.classList.remove('on'));
  document.getElementById('view-' + v).classList.add('on');
  document.querySelector(`.nb[data-view="${v}"]`).classList.add('on');
}

// ── status ────────────────────────────────────────────────────────────────────
async function loadStatus() {
  try {
    const d = await fetch('/api/status').then(r => r.json());
    S.svcs = d.services; S.profiles = d.profiles; S.lanIp = d.lan_ip;
    renderDash();
  } catch(e) {}
}

// ── profiles ──────────────────────────────────────────────────────────────────
async function toggleProfile(name) {
  const p = [...S.profiles];
  const i = p.indexOf(name);
  i === -1 ? p.push(name) : p.splice(i, 1);
  await api('/api/config', {profiles: p});
  S.profiles = p;
  renderDash();
  toast(`Profile "${name}" ${p.includes(name) ? 'enabled' : 'disabled'}`, 'inf');
}

// ── render dashboard ──────────────────────────────────────────────────────────
function renderDash() {
  renderPills();
  renderCards();
  renderHealth();
}

function renderPills() {
  const allP = [...new Set(SVC_META.filter(s => s.profile).map(s => s.profile))];
  document.getElementById('pills').innerHTML = allP.map(p => `
    <button class="pill ${S.profiles.includes(p)?'on':''}" onclick="toggleProfile('${p}')">
      <span class="pill-dot"></span>${p}
    </button>`).join('');
}

function renderHealth() {
  const active = S.svcs.filter(s => s.profile_active);
  const run = active.filter(s => s.state === 'running').length;
  const dot = document.getElementById('hdot');
  dot.className = 'hdot';
  if (run === 0)               { dot.classList.add('down');    document.getElementById('htxt').textContent = 'All stopped'; }
  else if (run < active.length){ dot.classList.add('partial'); document.getElementById('htxt').textContent = `${run}/${active.length} running`; }
  else                         { dot.classList.add('up');      document.getElementById('htxt').textContent = `${run}/${active.length} running`; }
}

function svcUrl(svc) {
  const h = ['localhost','127.0.0.1','::1'].includes(location.hostname) ? location.hostname : S.lanIp;
  return `http://${h}:${svc.port}${svc.path || '/'}`;
}

function scClass(st) {
  if (st === 'running') return 'running';
  if (st === 'exited' || st === 'stopped') return 'exited';
  if (st === 'restarting') return 'restarting';
  return 'not_created';
}
function scLabel(st) {
  return {running:'● Running',exited:'○ Exited',stopped:'○ Stopped',
          restarting:'↺ Restarting',not_created:'· Not created',created:'· Created'}[st] || st;
}

function cardHTML(s) {
  const sc = scClass(s.state);
  const run = s.state === 'running';
  const hasUI = s.path != null;
  const pend = S.pending.has(s.name);
  const iconBg = s.color + '1e';
  const iconBr = s.color + '44';
  return `
<div class="card ${s.profile_active?'':'dim'}" id="card-${s.name}">
  <div class="ca" style="background:${s.color}"></div>
  <div class="cb">
    ${s.profile ? `<div class="stag">${s.profile}</div>` : ''}
    <div class="ch">
      <div class="ci" style="background:${iconBg};border:1px solid ${iconBr}">${s.icon}</div>
      <div class="cm">
        <div class="cn">${s.label}</div>
        <div class="cd">${s.desc}</div>
        <div class="cp">:${s.port}${s.buildable ? ' · build' : ''}</div>
      </div>
      <div class="sbadge ${sc}"><div class="sdot"></div>${scLabel(s.state)}</div>
    </div>
    <div class="cact">
      <button class="btn sm pri" onclick="svcAct('${s.name}','start')" ${run||pend?'disabled':''}>▶</button>
      <button class="btn sm dng" onclick="svcAct('${s.name}','stop')" ${!run||pend?'disabled':''}>■</button>
      <button class="btn sm" onclick="svcAct('${s.name}','restart')" ${pend?'disabled':''}>↺</button>
      <button class="btn sm" onclick="svcAct('${s.name}','pull')" title="${s.buildable?'Rebuild':'Pull'} & recreate" ${pend?'disabled':''}>⬇</button>
      <button class="btn sm" onclick="openLogs('${s.name}')" title="View logs">📋</button>
      ${hasUI && run ? `<a class="btn sm open-btn" href="${svcUrl(s)}" target="_blank" rel="noopener">Open ↗</a>` : ''}
    </div>
  </div>
</div>`;
}

function renderCards() {
  const core = S.svcs.filter(s => !s.profile);
  const byProf = {};
  S.svcs.filter(s => s.profile).forEach(s => {
    (byProf[s.profile] = byProf[s.profile] || []).push(s);
  });

  let html = `<div class="sec"><div class="sec-hdr"><span class="sec-title">Core services</span><div class="sec-line"></div></div><div class="grid">`;
  core.forEach(s => { html += cardHTML(s); });
  html += '</div></div>';

  for (const [prof, svcs] of Object.entries(byProf)) {
    html += `<div class="sec"><div class="sec-hdr"><span class="sec-title">${prof} profile</span><div class="sec-line"></div></div><div class="grid">`;
    svcs.forEach(s => { html += cardHTML(s); });
    html += '</div></div>';
  }

  document.getElementById('svc-container').innerHTML = html;
}

// ── service actions ───────────────────────────────────────────────────────────
async function svcAct(name, action) {
  if (S.pending.has(name)) return;
  S.pending.add(name);
  const label = {start:'Starting',stop:'Stopping',restart:'Restarting',pull:'Updating'}[action];
  toast(`${label} ${name}…`, 'inf');
  renderCards();
  try {
    const d = await api(`/api/service/${name}/${action}`);
    toast(`${name}: ${action} done`, d.ok ? 'ok' : 'err');
    if (!d.ok && d.err) toast(d.err.slice(0,120), 'err');
  } catch(e) { toast(`${name}: request failed`, 'err'); }
  S.pending.delete(name);
  await loadStatus();
}

async function stackAct(action) {
  const label = {start:'Starting',stop:'Stopping',restart:'Restarting',pull:'Pulling images for'}[action];
  toast(`${label} stack…`, 'inf');
  try {
    const d = await api(`/api/stack/${action}`);
    toast('Stack ' + action + ' done', d.ok ? 'ok' : 'err');
    if (!d.ok && d.err) toast(d.err.slice(0,120), 'err');
  } catch(e) { toast('Request failed', 'err'); }
  await loadStatus();
}

// ── .env ──────────────────────────────────────────────────────────────────────
async function loadEnv() {
  try {
    const d = await fetch('/api/env').then(r => r.json());
    document.getElementById('eta').value = d.content;
    S.envOrig = d.content; S.envDeps = d.env_deps || {};
  } catch(e) {}
}

async function loadExample() {
  if (!confirm('Replace .env content with .env.example defaults?')) return;
  const d = await fetch('/api/env/example').then(r => r.json());
  document.getElementById('eta').value = d.content;
  onEnvChange();
}

async function saveEnv() {
  const content = document.getElementById('eta').value;
  await api('/api/env', null, 'POST', {content});
  S.envOrig = content;
  toast('Saved .env', 'ok');
  onEnvChange();
}

function onEnvChange() {
  const cur = document.getElementById('eta').value;
  const changed = diffKeys(S.envOrig, cur);
  const aff = new Set();
  changed.forEach(k => (S.envDeps[k] || []).forEach(s => aff.add(s)));
  const banner = document.getElementById('rbanner');
  if (aff.size) {
    banner.classList.add('on');
    document.getElementById('rbl').innerHTML = [...aff].map(s =>
      `<span class="rchip">${s}</span>`).join('');
  } else {
    banner.classList.remove('on');
  }
}

function diffKeys(a, b) {
  const parse = t => {
    const m = {};
    t.split('\n').forEach(l => {
      l = l.trim();
      if (l && !l.startsWith('#')) { const eq = l.indexOf('='); if (eq > 0) m[l.slice(0,eq).trim()] = l.slice(eq+1); }
    });
    return m;
  };
  const pa = parse(a), pb = parse(b);
  return [...new Set([...Object.keys(pa),...Object.keys(pb)])].filter(k => pa[k] !== pb[k]);
}

// ── logs ──────────────────────────────────────────────────────────────────────
function populateLogSel() {
  const sel = document.getElementById('lsel');
  SVC_META.forEach(s => {
    const o = document.createElement('option');
    o.value = s.name; o.textContent = s.icon + ' ' + s.label;
    sel.appendChild(o);
  });
}

function openLogs(name) {
  nav('logs');
  document.getElementById('lsel').value = name;
  startLogs();
}

function startLogs() {
  const svc = document.getElementById('lsel').value;
  if (!svc) return;
  if (S.logEs) { S.logEs.close(); S.logEs = null; }
  clearLog();
  document.getElementById('lout').textContent = `Connecting to ${svc} logs…\n`;
  S.logEs = new EventSource(`/api/logs/${svc}`);
  S.logEs.onmessage = e => appendLog(JSON.parse(e.data));
  S.logEs.onerror = () => appendLog('[stream ended]');
}

function appendLog(line) {
  const out = document.getElementById('lout');
  const d = document.createElement('div');
  const lo = line.toLowerCase();
  if (/error|fatal|critical/.test(lo)) d.className = 'll-err';
  else if (/warn/.test(lo)) d.className = 'll-warn';
  else if (/info|started|ready|listening/.test(lo)) d.className = 'll-ok';
  d.textContent = line;
  out.appendChild(d);
  if (out.children.length > 2000) out.removeChild(out.firstChild);
  if (S.logFollow) out.scrollTop = out.scrollHeight;
}

function clearLog() { document.getElementById('lout').innerHTML = ''; }

function toggleFollow() {
  S.logFollow = !S.logFollow;
  document.getElementById('lfbtn').textContent = S.logFollow ? '📌 Following' : '⏸ Paused';
}

// ── toasts ────────────────────────────────────────────────────────────────────
function toast(msg, type='inf') {
  const icons = {ok:'✅',err:'❌',inf:'ℹ️'};
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span>${icons[type]||'ℹ️'}</span><span>${msg}</span>`;
  document.getElementById('tc').appendChild(el);
  setTimeout(() => el.remove(), 4500);
}

// ── fetch helper ──────────────────────────────────────────────────────────────
async function api(url, body, method='POST', data=body) {
  const opts = {method, headers:{'Content-Type':'application/json'}};
  if (data !== null && data !== undefined) opts.body = JSON.stringify(data);
  const r = await fetch(url, opts);
  return r.json();
}
</script>
</body>
</html>"""

# ── server ────────────────────────────────────────────────────────────────────

class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

if __name__ == "__main__":
    for arg in sys.argv[1:]:
        if arg.startswith("--port="):  PORT = int(arg.split("=",1)[1])
        elif arg.startswith("--host="): HOST = arg.split("=",1)[1]
    print(f"AI Stack Dashboard → http://localhost:{PORT}")
    print(f"Stack directory: {STACK_DIR}")
    Server((HOST, PORT), Handler).serve_forever()
