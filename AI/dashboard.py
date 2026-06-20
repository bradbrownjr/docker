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
    dict(name="ntfy",      label="ntfy",         port=8091,  path="/",     color="#0284c7", icon="🔔", profile=None,       buildable=False, desc="Push notifications"),
    dict(name="voicebox",  label="Voicebox",     port=17493, path="/",     color="#4f46e5", icon="🎙️", profile="voicebox", buildable=True,  desc="Voice cloning & studio"),
    dict(name="odysseus",  label="Odysseus",     port=7000,  path="/",     color="#d97706", icon="🚢", profile="odysseus", buildable=True,  desc="AI agent platform"),
    dict(name="chromadb",  label="ChromaDB",     port=8100,  path="/docs", color="#059669", icon="🗄️", profile="odysseus", buildable=False, desc="Vector database"),
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

def gpu_stats():
    try:
        r = subprocess.run(
            ["nvidia-smi","--query-gpu=gpu_name,memory.used,memory.total,utilization.gpu,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5)
        if r.returncode != 0: return None
        gpus = []
        for line in r.stdout.strip().splitlines():
            p = [x.strip() for x in line.split(",")]
            if len(p) >= 5:
                gpus.append({"name":p[0],"vram_used":int(p[1]),"vram_total":int(p[2]),
                             "util":int(p[3]),"temp":int(p[4])})
        return gpus or None
    except: return None

def ollama_models():
    try:
        r = subprocess.run(["docker","exec","ollama","ollama","ps"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode != 0: return []
        lines = r.stdout.strip().splitlines()
        if len(lines) < 2: return []
        models = []
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 4:
                models.append({"name":parts[0],"id":parts[1],"size":parts[2]+" "+parts[3],
                               "proc":parts[4] if len(parts)>4 else "","until":" ".join(parts[5:]) if len(parts)>5 else ""})
        return models
    except: return []

def parse_env_fields():
    """Parse .env.example into structured sections; merge current .env values."""
    ex = STACK_DIR / ".env.example"
    if not ex.exists(): return []
    cur = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            s = line.strip()
            if s and not s.startswith('#') and '=' in s:
                k, _, v = s.partition('='); cur[k.strip()] = v
    sections, sec_name, fields, desc_buf = [], "General", [], []
    def flush_sec():
        nonlocal sec_name, fields
        if fields: sections.append({"name": sec_name, "fields": fields})
        fields = []
    for line in ex.read_text().splitlines():
        s = line.strip()
        if not s: desc_buf = []; continue
        is_divider = s.startswith('#') and len(s) > 8 and all(c in '#-= \t' for c in s)
        if is_divider: continue
        if s.startswith('#'):
            txt = s.lstrip('#').strip()
            if txt: desc_buf.append(txt)
        elif '=' in s:
            k, _, default = s.partition('='); k = k.strip()
            # Detect if this comment block is really a section title (no prior key in this block)
            if desc_buf and not fields:
                flush_sec(); sec_name = desc_buf[0]; desc_buf = desc_buf[1:]
            fields.append({"key":k,"default":default,"value":cur.get(k,default),
                           "desc":" ".join(desc_buf).strip(),
                           "affects":ENV_DEPS.get(k,[]),
                           "secret":any(w in k.lower() for w in ["password","token","key","secret"])})
            desc_buf = []
    flush_sec()
    return sections

def save_env_fields(field_map):
    """Rebuild .env from .env.example template, substituting field_map values."""
    ex = STACK_DIR / ".env.example"
    if not ex.exists(): return False
    out = []
    for line in ex.read_text().splitlines():
        s = line.strip()
        if s and not s.startswith('#') and '=' in s:
            k = s.partition('=')[0].strip()
            if k in field_map:
                out.append(f"{k}={field_map[k]}")
                continue
        out.append(line)
    ENV_FILE.write_text("\n".join(out) + "\n")
    return True

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
        if p in ("/","/index.html"):
            html = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length", len(html))
            self.end_headers(); self.wfile.write(html)
        elif p == "/api/status":
            self.send_json({"services":get_statuses(),"profiles":active_profiles(),"lan_ip":lan_ip()})
        elif p == "/api/gpu":
            self.send_json({"gpus":gpu_stats(),"models":ollama_models()})
        elif p == "/api/env":
            self.send_json({"content":ENV_FILE.read_text() if ENV_FILE.exists() else "","env_deps":ENV_DEPS})
        elif p == "/api/env/fields":
            self.send_json({"sections":parse_env_fields()})
        elif p == "/api/env/example":
            ex = STACK_DIR/".env.example"
            self.send_json({"content":ex.read_text() if ex.exists() else ""})
        elif p.startswith("/api/logs/"):
            self._stream_logs(p[len("/api/logs/"):])
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        p = urlparse(self.path).path; d = self.body()

        if p == "/api/env":
            ENV_FILE.write_text(d.get("content",""))
            self.send_json({"ok":True})
        elif p == "/api/env/fields":
            ok = save_env_fields(d.get("fields",{}))
            self.send_json({"ok":ok})
        elif p == "/api/config":
            cfg = load_cfg(); cfg.update(d); save_cfg(cfg)
            self.send_json({"ok":True})
        elif p.startswith("/api/service/"):
            parts = p[len("/api/service/"):].rsplit("/",1)
            name, action = parts[0], parts[1]
            svc = next((s for s in SERVICES if s["name"]==name), None)
            extra = [svc["profile"]] if svc and svc["profile"] else []
            if   action == "start":   r = compose_run(["up","-d","--remove-orphans",name], extra)
            elif action == "stop":    r = compose_run(["stop", name])
            elif action == "restart": r = compose_run(["restart", name], extra)
            elif action == "pull":
                if svc and svc.get("buildable"): compose_run(["build","--pull",name], extra, 600)
                else: compose_run(["pull",name], extra, 300)
                r = compose_run(["up","-d","--force-recreate",name], extra)
            else: self.send_response(404); self.end_headers(); return
            self.send_json(r)
        elif p.startswith("/api/section/"):
            parts = p[len("/api/section/"):].rsplit("/",1)
            sec, action = parts[0], parts[1]
            if sec == "core":
                names = [s["name"] for s in SERVICES if s["profile"] is None]
                extra = []
            else:
                names = [s["name"] for s in SERVICES if s["profile"]==sec]
                extra = [sec]
            if   action == "start":   r = compose_run(["up","-d","--remove-orphans"]+names, extra)
            elif action == "stop":    r = compose_run(["stop"]+names)
            elif action == "restart": r = compose_run(["restart"]+names, extra)
            else: self.send_response(404); self.end_headers(); return
            self.send_json(r)
        elif p == "/api/stack/start":   self.send_json(compose_run(["up","-d","--remove-orphans"]))
        elif p == "/api/stack/stop":    self.send_json(compose_run(["down"]))
        elif p == "/api/stack/restart": self.send_json(compose_run(["up","-d","--force-recreate","--remove-orphans"]))
        elif p == "/api/stack/pull":
            compose_run(["pull"], timeout=600)
            self.send_json(compose_run(["up","-d","--remove-orphans"]))
        else: self.send_response(404); self.end_headers()

    def _stream_logs(self, svc):
        self.send_response(200)
        self.send_header("Content-Type","text/event-stream")
        self.send_header("Cache-Control","no-cache")
        self.send_header("Connection","keep-alive")
        self.send_header("Access-Control-Allow-Origin","*")
        self.end_headers()
        cmd = compose_base(["voicebox","odysseus"]) + ["logs","--tail=200","-f",svc]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, cwd=str(STACK_DIR))
        try:
            for line in proc.stdout:
                self.wfile.write(f"data: {json.dumps(line.rstrip())}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError): pass
        finally: proc.terminate()

# ── HTML ──────────────────────────────────────────────────────────────────────

_SVC_JSON = json.dumps(SERVICES)

HTML = r"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Stack</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}

:root {
  --bg:#0d0d15; --surf:#1a1a2c; --surf2:#22223a; --surf3:#2a2a44;
  --bdr:#3a3a58; --bdr2:#52528a;
  --txt:#eaf0ff; --muted:#9aa0c8; --dim:#6068a0;
  --acc:#6366f1; --acc2:#818cf8; --accbg:rgba(99,102,241,.16);
  --grn:#22c55e; --grndim:rgba(34,197,94,.15); --grnbdr:rgba(34,197,94,.3);
  --ylw:#f59e0b; --ylwdim:rgba(245,158,11,.14); --ylwbdr:rgba(245,158,11,.3);
  --red:#f87171; --reddim:rgba(248,113,113,.12); --redbdr:rgba(248,113,113,.25);
  --r:12px; --rs:8px; --shadow:0 8px 40px rgba(0,0,0,.55);
  --tr:.16s ease;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
}
[data-theme=light]{
  --bg:#b8c4dc; --surf:#ffffff; --surf2:#eef2fa; --surf3:#e2e8f5;
  --bdr:#8fa0c0; --bdr2:#6e84a8;
  --txt:#080f22; --muted:#253555; --dim:#4a5e80;
  --acc:#2e29b8; --acc2:#3730a3; --accbg:rgba(46,41,184,.1);
  --grn:#15803d; --grndim:#dcfce7; --grnbdr:#86efac;
  --ylw:#92400e; --ylwdim:#fef3c7; --ylwbdr:#fcd34d;
  --red:#991b1b; --reddim:#fee2e2; --redbdr:#fca5a5;
  --shadow:0 4px 20px rgba(0,0,0,.18);
}

body{background:var(--bg);color:var(--txt);min-height:100vh;display:grid;
  grid-template-columns:210px 1fr;grid-template-rows:52px 1fr}

/* ── header ── */
header{grid-column:1/-1;background:var(--surf);border-bottom:2px solid var(--bdr);
  display:flex;align-items:center;padding:0 18px;gap:14px;z-index:50;position:sticky;top:0}
.logo{display:flex;align-items:center;gap:9px;font-weight:800;font-size:1rem;letter-spacing:-.02em}
.logo-mark{width:30px;height:30px;border-radius:8px;font-size:17px;
  background:linear-gradient(135deg,#6366f1,#a855f7);
  display:flex;align-items:center;justify-content:center}
.hsp{flex:1}
.health{display:flex;align-items:center;gap:7px;padding:5px 13px;border-radius:20px;
  background:var(--surf2);border:1.5px solid var(--bdr);font-size:.78rem;font-weight:700;color:var(--muted)}
.hdot{width:8px;height:8px;border-radius:50%;background:var(--dim)}
.hdot.up{background:var(--grn);box-shadow:0 0 8px var(--grn);animation:pulse 2.5s infinite}
.hdot.partial{background:var(--ylw)}
.hdot.down{background:var(--red)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
.icon-btn{width:34px;height:34px;border-radius:7px;background:var(--surf2);border:1.5px solid var(--bdr);
  color:var(--muted);cursor:pointer;font-size:16px;display:flex;align-items:center;
  justify-content:center;transition:var(--tr);border:1.5px solid var(--bdr)}
.icon-btn:hover{background:var(--surf3);color:var(--txt);border-color:var(--bdr2)}

/* ── nav ── */
nav{background:var(--surf);border-right:2px solid var(--bdr);padding:14px 10px;
  display:flex;flex-direction:column;gap:2px;overflow-y:auto}
.nl{font-size:.65rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase;
  color:var(--dim);padding:14px 10px 5px}
.nb{display:flex;align-items:center;gap:9px;padding:9px 10px;border-radius:var(--rs);
  border:none;background:none;color:var(--muted);cursor:pointer;font-size:.88rem;
  font-weight:600;transition:var(--tr);width:100%;text-align:left}
.nb:hover{background:var(--surf2);color:var(--txt)}
.nb.on{background:var(--accbg);color:var(--acc2);font-weight:700}
.nb .ni{font-size:17px;width:22px;text-align:center}

/* ── main ── */
main{padding:20px;overflow-y:auto;display:flex;flex-direction:column;gap:18px}
.view{display:none;flex-direction:column;gap:16px}
.view.on{display:flex}

/* ── buttons ── */
.btn{display:inline-flex;align-items:center;gap:5px;padding:7px 14px;border-radius:var(--rs);
  border:1.5px solid var(--bdr);background:var(--surf2);color:var(--txt);font-size:.82rem;
  font-weight:600;cursor:pointer;transition:var(--tr);white-space:nowrap;font-family:inherit}
.btn:hover{background:var(--surf3);border-color:var(--bdr2)}
.btn:active{transform:scale(.97)}
.btn.pri{background:var(--acc);border-color:var(--acc);color:#fff}
.btn.pri:hover{filter:brightness(1.15)}
.btn.dng{background:var(--reddim);border-color:var(--redbdr);color:var(--red)}
.btn.dng:hover{filter:brightness(1.1)}
.btn.sm{padding:5px 10px;font-size:.76rem}
.btn:disabled{opacity:.3;cursor:not-allowed;transform:none!important}
.btn.ghost{background:none;border-color:transparent;color:var(--muted)}
.btn.ghost:hover{background:var(--surf2);border-color:var(--bdr);color:var(--txt)}

/* ── stack bar ── */
.sbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:10px 14px;
  background:var(--surf);border:1.5px solid var(--bdr);border-radius:var(--r)}
.sbar-lbl{font-size:.75rem;font-weight:800;letter-spacing:.07em;text-transform:uppercase;
  color:var(--muted);margin-right:4px}

/* ── GPU panel ── */
.gpu-panel{background:var(--surf);border:1.5px solid var(--bdr);border-radius:var(--r);
  padding:14px 16px;display:flex;flex-direction:column;gap:10px}
.gpu-hdr{display:flex;align-items:center;gap:8px;font-size:.8rem;font-weight:700;color:var(--muted)}
.gpu-hdr-title{color:var(--txt);font-size:.9rem}
.gpu-rows{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media(max-width:700px){.gpu-rows{grid-template-columns:1fr}}
.gpu-card{background:var(--surf2);border:1.5px solid var(--bdr);border-radius:var(--rs);padding:12px}
.gpu-name{font-weight:700;font-size:.85rem;margin-bottom:8px;display:flex;align-items:center;
  justify-content:space-between}
.gpu-temp{font-size:.75rem;font-weight:700;padding:2px 7px;border-radius:20px;
  background:var(--ylwdim);border:1px solid var(--ylwbdr);color:var(--ylw)}
.vbar-wrap{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.vbar-lbl{font-size:.72rem;color:var(--muted);white-space:nowrap;width:32px}
.vbar-track{flex:1;height:10px;border-radius:5px;background:var(--surf3);overflow:hidden;border:1px solid var(--bdr)}
.vbar-fill{height:100%;border-radius:5px;transition:width .5s ease;background:linear-gradient(90deg,#6366f1,#a855f7)}
.vbar-fill.warn{background:linear-gradient(90deg,#f59e0b,#ef4444)}
.vbar-nums{font-size:.71rem;color:var(--muted);text-align:right}
.gpu-util{display:flex;gap:16px;font-size:.75rem;margin-top:4px}
.gpu-util span{display:flex;align-items:center;gap:4px;color:var(--muted)}
.gpu-util strong{color:var(--txt)}
.ollama-table{font-size:.78rem;border-collapse:collapse;width:100%}
.ollama-table th{text-align:left;padding:5px 8px;color:var(--muted);font-weight:700;
  border-bottom:1.5px solid var(--bdr);font-size:.7rem;letter-spacing:.05em;text-transform:uppercase}
.ollama-table td{padding:5px 8px;border-bottom:1px solid var(--bdr)}
.ollama-table tr:last-child td{border-bottom:none}
.ollama-empty{font-size:.78rem;color:var(--dim);font-style:italic;padding:4px 0}
.gpu-none{font-size:.8rem;color:var(--dim);font-style:italic;text-align:center;padding:8px}

/* ── section ── */
.sec{display:flex;flex-direction:column;gap:10px}
#svc-container{display:flex;flex-direction:column;gap:28px}
.sec-hdr{display:flex;align-items:center;gap:8px}
.sec-title{font-size:.75rem;font-weight:800;letter-spacing:.07em;text-transform:uppercase;
  color:var(--muted);white-space:nowrap}
.sec-line{flex:1;height:1.5px;background:var(--bdr)}
.sec-acts{display:flex;gap:5px;align-items:center;flex-shrink:0}
.ptoggle{display:flex;align-items:center;gap:5px;padding:4px 10px;border-radius:20px;
  border:1.5px solid var(--bdr);background:var(--surf2);font-size:.74rem;font-weight:700;
  cursor:pointer;transition:var(--tr);color:var(--muted);font-family:inherit}
.ptoggle.on{border-color:var(--acc);background:var(--accbg);color:var(--acc2)}
.pdot{width:6px;height:6px;border-radius:50%;background:currentColor}

/* ── service grid ── */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}

/* ── service card ── */
.card{background:var(--surf);border:1.5px solid var(--bdr);border-radius:var(--r);
  overflow:hidden;transition:border-color var(--tr),box-shadow var(--tr)}
.card:hover{border-color:var(--bdr2);box-shadow:var(--shadow)}
.card.inactive{opacity:.55;filter:saturate(.35)}
.card.inactive .cact .btn:not(.open-btn){opacity:.4;cursor:not-allowed}
.ca{height:3px}
.cb{padding:14px}
.ch{display:flex;align-items:flex-start;gap:10px;margin-bottom:12px}
.ci{width:40px;height:40px;border-radius:9px;display:flex;align-items:center;
  justify-content:center;font-size:20px;flex-shrink:0}
.cm{flex:1;min-width:0}
.cn{font-weight:800;font-size:.92rem;color:var(--txt)}
.cd{font-size:.74rem;color:var(--muted);margin-top:2px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cp{font-size:.68rem;color:var(--dim);margin-top:3px;font-family:'SF Mono','Fira Code',monospace}
.stag{display:inline-block;font-size:.6rem;font-weight:800;letter-spacing:.06em;
  text-transform:uppercase;padding:2px 6px;border-radius:4px;background:var(--surf3);
  color:var(--dim);border:1.5px solid var(--bdr);margin-bottom:6px}

/* ── status badge ── */
.sbadge{display:inline-flex;align-items:center;gap:4px;padding:3px 8px;
  border-radius:20px;font-size:.7rem;font-weight:700;flex-shrink:0;letter-spacing:.01em}
.sbadge.running{background:var(--grndim);border:1px solid var(--grnbdr);color:var(--grn)}
.sbadge.exited,.sbadge.stopped{background:var(--reddim);border:1px solid var(--redbdr);color:var(--red)}
.sbadge.restarting{background:var(--ylwdim);border:1px solid var(--ylwbdr);color:var(--ylw)}
.sbadge.not_created,.sbadge.created{background:var(--surf3);border:1px solid var(--bdr2);color:var(--dim)}
.sdot{width:5px;height:5px;border-radius:50%;background:currentColor}

/* ── card actions ── */
.cact{display:flex;gap:5px;flex-wrap:wrap;align-items:center}
.open-btn{margin-left:auto}

/* ── .env editor ── */
.env-wrap{display:flex;flex-direction:column;gap:0;background:var(--surf);
  border:1.5px solid var(--bdr);border-radius:var(--r);overflow:hidden}
.env-toolbar{display:flex;align-items:center;gap:8px;padding:11px 15px;
  border-bottom:1.5px solid var(--bdr);background:var(--surf2)}
.env-toolbar-title{font-size:.88rem;font-weight:800}
.env-mode-btns{display:flex;border:1.5px solid var(--bdr);border-radius:var(--rs);overflow:hidden}
.env-mode-btn{padding:4px 12px;font-size:.75rem;font-weight:700;cursor:pointer;
  background:none;border:none;color:var(--muted);font-family:inherit;transition:var(--tr)}
.env-mode-btn.on{background:var(--acc);color:#fff}
/* fields mode */
.env-fields{padding:16px;display:flex;flex-direction:column;gap:0}
.env-section{margin-bottom:20px}
.env-sec-title{font-size:.72rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;
  color:var(--muted);padding-bottom:8px;border-bottom:1.5px solid var(--bdr);margin-bottom:12px}
.env-field{display:grid;grid-template-columns:200px 1fr auto;align-items:start;
  gap:10px;padding:8px 0;border-bottom:1px solid var(--bdr)}
.env-field:last-child{border-bottom:none}
.env-field-lbl{display:flex;flex-direction:column;gap:3px}
.env-field-key{font-family:'SF Mono','Fira Code',monospace;font-size:.78rem;font-weight:700;color:var(--txt)}
.env-field-desc{font-size:.7rem;color:var(--muted);line-height:1.4}
.env-field-input{padding:6px 10px;border-radius:var(--rs);border:1.5px solid var(--bdr);
  background:var(--surf2);color:var(--txt);font-size:.82rem;font-family:inherit;
  outline:none;transition:border-color var(--tr);width:100%}
.env-field-input:focus{border-color:var(--acc)}
.env-field-affects{display:flex;flex-wrap:wrap;gap:4px;min-width:80px;justify-content:flex-end}
.aff-chip{font-size:.65rem;font-weight:700;padding:2px 6px;border-radius:4px;
  background:var(--surf3);border:1px solid var(--bdr2);color:var(--dim)}
/* raw mode */
.env-raw{width:100%;min-height:70vh;background:var(--surf);color:var(--txt);border:none;
  outline:none;resize:none;font-family:'SF Mono','Fira Code',monospace;
  font-size:.8rem;line-height:1.75;padding:16px;tab-size:2}
/* restart banner */
.rbanner{display:none;align-items:flex-start;gap:10px;padding:12px 15px;
  background:var(--ylwdim);border-top:1.5px solid var(--ylwbdr);color:var(--ylw);font-size:.8rem}
.rbanner.on{display:flex}
.rbl{margin-top:6px;display:flex;flex-wrap:wrap;gap:5px}
.rchip{padding:2px 8px;border-radius:4px;background:var(--ylwdim);
  border:1px solid var(--ylwbdr);font-size:.72rem;font-weight:700;color:var(--ylw)}

/* ── logs ── */
.lctrl{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.lsel{padding:7px 12px;border-radius:var(--rs);border:1.5px solid var(--bdr);
  background:var(--surf);color:var(--txt);font-size:.83rem;cursor:pointer;
  outline:none;min-width:170px;font-family:inherit;font-weight:600}
.lout{background:#05050a;border:1.5px solid var(--bdr);border-radius:var(--r);
  font-family:'SF Mono','Fira Code',monospace;font-size:.76rem;line-height:1.65;
  color:#8899bb;padding:14px;height:560px;overflow-y:auto;white-space:pre-wrap;word-break:break-all}
[data-theme=light] .lout{background:#111827;color:#9ba8c0}
.ll-err{color:#f87171}.ll-warn{color:#fbbf24}.ll-ok{color:#6ee7b7}

/* ── toasts ── */
#tc{position:fixed;bottom:20px;right:20px;display:flex;flex-direction:column;gap:8px;z-index:9999}
.toast{padding:10px 16px;border-radius:var(--rs);background:var(--surf);border:1.5px solid var(--bdr);
  box-shadow:var(--shadow);font-size:.82rem;font-weight:600;display:flex;align-items:center;
  gap:9px;max-width:300px;animation:tin .16s ease}
.toast.ok{border-left:3px solid var(--grn)}
.toast.err{border-left:3px solid var(--red)}
.toast.inf{border-left:3px solid var(--acc)}
@keyframes tin{from{transform:translateX(14px);opacity:0}to{transform:none;opacity:1}}

@media(max-width:680px){
  body{grid-template-columns:1fr;grid-template-rows:52px auto 1fr}
  nav{flex-direction:row;border-right:none;border-bottom:2px solid var(--bdr);overflow-x:auto;padding:6px}
  .nl{display:none}.grid{grid-template-columns:1fr}
  .env-field{grid-template-columns:1fr;gap:6px}
  .env-field-affects{justify-content:flex-start}
}
</style>
</head>
<body>
<header>
  <div class="logo"><div class="logo-mark">🤖</div><span>AI Stack</span></div>
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
    <!-- GPU + Ollama panel -->
    <div class="gpu-panel" id="gpu-panel">
      <div class="gpu-hdr">
        <span class="gpu-hdr-title">🖥 GPU &amp; Models</span>
        <span id="gpu-updated" style="margin-left:auto;font-size:.7rem;color:var(--dim)"></span>
      </div>
      <div id="gpu-content"><div class="gpu-none">Loading…</div></div>
    </div>
    <!-- Stack bar -->
    <div class="sbar">
      <span class="sbar-lbl">Stack</span>
      <button class="btn sm pri" onclick="stackAct('start')">▶ Start</button>
      <button class="btn sm" onclick="stackAct('restart')">↺ Restart</button>
      <button class="btn sm dng" onclick="stackAct('stop')">■ Stop</button>
      <button class="btn sm" onclick="stackAct('pull')" title="Pull latest images &amp; recreate">⬇ Update All</button>
    </div>
    <!-- Service sections -->
    <div id="svc-container"></div>
  </div>

  <!-- .env Editor -->
  <div class="view" id="view-env">
    <div class="env-wrap">
      <div class="env-toolbar">
        <span class="env-toolbar-title">⚙️ .env</span>
        <div class="env-mode-btns">
          <button class="env-mode-btn on" id="mf" onclick="setEnvMode('fields')">Fields</button>
          <button class="env-mode-btn" id="mr" onclick="setEnvMode('raw')">Raw</button>
        </div>
        <div class="hsp"></div>
        <button class="btn sm ghost" onclick="loadExample()">↩ Reset</button>
        <button class="btn sm pri" onclick="saveEnv()">💾 Save</button>
      </div>
      <div id="env-fields-view" class="env-fields"></div>
      <textarea id="env-raw-view" class="env-raw" style="display:none" spellcheck="false"></textarea>
      <div class="rbanner" id="rbanner">
        <span style="font-size:16px;flex-shrink:0">⚠️</span>
        <div>
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
const SVC_META = """ + _SVC_JSON + r""";

const S = {
  svcs:[], profiles:[], lanIp:'127.0.0.1',
  theme: localStorage.getItem('theme')||'dark',
  logEs:null, logFollow:true,
  envMode:'fields', envOrig:'', envDeps:{}, envFields:[],
  pending:new Set(),
};

// ── boot ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  applyTheme(S.theme);
  loadStatus(); loadEnv(); loadGpu(); populateLogSel();
  setInterval(loadStatus, 4000);
  setInterval(loadGpu, 5000);
  document.querySelectorAll('.nb[data-view]').forEach(b =>
    b.addEventListener('click', () => nav(b.dataset.view)));
});

// ── theme ─────────────────────────────────────────────────────────────────────
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  document.getElementById('tbtn').textContent = t==='dark' ? '☀️' : '🌙';
  localStorage.setItem('theme', t); S.theme = t;
}
document.getElementById('tbtn').addEventListener('click',
  () => applyTheme(S.theme==='dark' ? 'light' : 'dark'));

// ── nav ───────────────────────────────────────────────────────────────────────
function nav(v) {
  document.querySelectorAll('.view').forEach(el => el.classList.remove('on'));
  document.querySelectorAll('.nb').forEach(b => b.classList.remove('on'));
  document.getElementById('view-'+v).classList.add('on');
  document.querySelector(`.nb[data-view="${v}"]`).classList.add('on');
}

// ── status polling ────────────────────────────────────────────────────────────
async function loadStatus() {
  try {
    const d = await fetch('/api/status').then(r=>r.json());
    S.svcs=d.services; S.profiles=d.profiles; S.lanIp=d.lan_ip;
    renderDash();
  } catch(e) {}
}

// ── profiles ──────────────────────────────────────────────────────────────────
async function toggleProfile(name) {
  const p=[...S.profiles]; const i=p.indexOf(name);
  i===-1 ? p.push(name) : p.splice(i,1);
  await api('/api/config',{profiles:p});
  S.profiles=p; renderDash();
  toast(`"${name}" profile ${p.includes(name)?'enabled':'disabled'}`,'inf');
}

// ── dashboard ─────────────────────────────────────────────────────────────────
function renderDash() { renderHealth(); renderCards(); }

function renderHealth() {
  const active=S.svcs.filter(s=>s.profile_active);
  const run=active.filter(s=>s.state==='running').length;
  const dot=document.getElementById('hdot');
  const txt=document.getElementById('htxt');
  dot.className='hdot';
  if(run===0){dot.classList.add('down');txt.textContent='All stopped';}
  else if(run<active.length){dot.classList.add('partial');txt.textContent=`${run}/${active.length} running`;}
  else{dot.classList.add('up');txt.textContent=`${run}/${active.length} running`;}
}

function svcUrl(svc) {
  const h=['localhost','127.0.0.1','::1'].includes(location.hostname)?location.hostname:S.lanIp;
  return `http://${h}:${svc.port}${svc.path||'/'}`;
}

function scClass(st){
  if(st==='running')return'running';
  if(st==='exited'||st==='stopped')return'exited';
  if(st==='restarting')return'restarting';
  return'not_created';
}
function scLabel(st){
  return{running:'● Running',exited:'○ Exited',stopped:'○ Stopped',
         restarting:'↺ Restarting',not_created:'· Not created',created:'· Created'}[st]||st;
}

function cardHTML(svc) {
  const sc=scClass(svc.state);
  const run=svc.state==='running';
  const hasUI=svc.path!=null;
  const pend=S.pending.has(svc.name);
  const inact=!svc.profile_active;
  const cls='card'+(inact?' inactive':'');
  const ib=svc.color+'1a'; const ibr=svc.color+'55';
  const dis=pend||inact;
  return `
<div class="${cls}" id="card-${svc.name}">
  <div class="ca" style="background:${svc.color}"></div>
  <div class="cb">
    ${svc.profile?`<div class="stag">${svc.profile}</div>`:''}
    <div class="ch">
      <div class="ci" style="background:${ib};border:1px solid ${ibr}">${svc.icon}</div>
      <div class="cm">
        <div class="cn">${svc.label}</div>
        <div class="cd">${svc.desc}</div>
        <div class="cp">:${svc.port}${svc.buildable?' · build':''}</div>
      </div>
      <div class="sbadge ${sc}"><div class="sdot"></div>${scLabel(svc.state)}</div>
    </div>
    <div class="cact">
      <button class="btn sm pri" onclick="svcAct('${svc.name}','start')" ${run||dis?'disabled':''}>▶</button>
      <button class="btn sm dng" onclick="svcAct('${svc.name}','stop')" ${!run||dis?'disabled':''}>■</button>
      <button class="btn sm" onclick="svcAct('${svc.name}','restart')" ${dis?'disabled':''}>↺</button>
      <button class="btn sm" onclick="svcAct('${svc.name}','pull')" title="${svc.buildable?'Rebuild':'Pull'} &amp; recreate" ${dis?'disabled':''}>⬇</button>
      <button class="btn sm ghost" onclick="openLogs('${svc.name}')" title="Logs">📋</button>
      ${hasUI&&run?`<a class="btn sm open-btn" href="${svcUrl(svc)}" target="_blank" rel="noopener">Open ↗</a>`:''}
    </div>
  </div>
</div>`;
}

function sectionHTML(title, svcs, profile) {
  const isActive = profile===null || S.profiles.includes(profile);
  const secKey = profile||'core';
  let h = `<div class="sec"><div class="sec-hdr">
    <span class="sec-title">${title}</span>`;
  if(profile) {
    h += `<button class="ptoggle ${isActive?'on':''}" onclick="toggleProfile('${profile}')">
      <span class="pdot"></span>${isActive?'Active':'Inactive'}</button>`;
  }
  h += `<div class="sec-line"></div><div class="sec-acts">`;
  if(isActive) {
    h += `<button class="btn sm" onclick="secAct('${secKey}','start')">▶</button>
          <button class="btn sm" onclick="secAct('${secKey}','restart')">↺</button>
          <button class="btn sm dng" onclick="secAct('${secKey}','stop')">■</button>`;
  }
  h += `</div></div><div class="grid">`;
  svcs.forEach(s => { h += cardHTML(s); });
  h += `</div></div>`;
  return h;
}

function renderCards() {
  const core = S.svcs.filter(s=>!s.profile);
  const byProf = {};
  S.svcs.filter(s=>s.profile).forEach(s=>{(byProf[s.profile]=byProf[s.profile]||[]).push(s);});
  let h = sectionHTML('Core Services', core, null);
  for(const [prof,svcs] of Object.entries(byProf))
    h += sectionHTML(prof.charAt(0).toUpperCase()+prof.slice(1)+' Profile', svcs, prof);
  document.getElementById('svc-container').innerHTML = h;
}

// ── service actions ───────────────────────────────────────────────────────────
async function svcAct(name, action) {
  if(S.pending.has(name)) return;
  S.pending.add(name); renderCards();
  const label={start:'Starting',stop:'Stopping',restart:'Restarting',pull:'Updating'}[action];
  toast(`${label} ${name}…`,'inf');
  try {
    const d=await api(`/api/service/${name}/${action}`);
    toast(`${name}: ${action} done`, d.ok?'ok':'err');
    if(!d.ok&&d.err) toast(d.err.slice(0,120),'err');
  } catch(e){ toast(`${name}: failed`,'err'); }
  S.pending.delete(name); await loadStatus();
}

async function stackAct(action) {
  toast(`Stack ${action}…`,'inf');
  try{const d=await api(`/api/stack/${action}`);toast('Stack '+action+' done',d.ok?'ok':'err');}
  catch(e){toast('Failed','err');}
  await loadStatus();
}

async function secAct(sec, action) {
  toast(`${sec}: ${action}…`,'inf');
  try{const d=await api(`/api/section/${sec}/${action}`);toast(`${sec}: ${action} done`,d.ok?'ok':'err');}
  catch(e){toast('Failed','err');}
  await loadStatus();
}

// ── GPU panel ─────────────────────────────────────────────────────────────────
async function loadGpu() {
  try {
    const d=await fetch('/api/gpu').then(r=>r.json());
    renderGpu(d.gpus, d.models);
    document.getElementById('gpu-updated').textContent =
      'updated '+new Date().toLocaleTimeString();
  } catch(e){}
}

function renderGpu(gpus, models) {
  const el=document.getElementById('gpu-content');
  let h='<div class="gpu-rows">';

  // GPU cards
  if(!gpus||gpus.length===0) {
    h+=`<div class="gpu-none">No NVIDIA GPU detected or nvidia-smi not available</div>`;
  } else {
    gpus.forEach(g=>{
      const pct=Math.round(g.vram_used/g.vram_total*100);
      const warn=pct>85;
      h+=`<div class="gpu-card">
        <div class="gpu-name">${g.name} <span class="gpu-temp">${g.temp}°C</span></div>
        <div class="vbar-wrap">
          <span class="vbar-lbl">VRAM</span>
          <div class="vbar-track"><div class="vbar-fill${warn?' warn':''}" style="width:${pct}%"></div></div>
        </div>
        <div class="vbar-nums">${g.vram_used} / ${g.vram_total} MB &nbsp;(${pct}%)</div>
        <div class="gpu-util">
          <span>GPU <strong>${g.util}%</strong></span>
        </div>
      </div>`;
    });
  }

  // Ollama models
  h+=`<div class="gpu-card"><div class="gpu-name" style="margin-bottom:10px">🦙 Ollama — Running Models</div>`;
  if(!models||models.length===0){
    h+=`<div class="ollama-empty">No models currently loaded</div>`;
  } else {
    h+=`<table class="ollama-table"><thead><tr>
      <th>Model</th><th>Size</th><th>Processor</th><th>Expires</th>
    </tr></thead><tbody>`;
    models.forEach(m=>{h+=`<tr><td>${m.name}</td><td>${m.size}</td><td>${m.proc}</td><td>${m.until}</td></tr>`;});
    h+=`</tbody></table>`;
  }
  h+=`</div></div>`;
  el.innerHTML=h;
}

// ── .env editor ───────────────────────────────────────────────────────────────
async function loadEnv() {
  try {
    const [fd,rd]=await Promise.all([
      fetch('/api/env/fields').then(r=>r.json()),
      fetch('/api/env').then(r=>r.json()),
    ]);
    S.envFields=fd.sections; S.envDeps=rd.env_deps||{};
    S.envOrig=rd.content;
    document.getElementById('env-raw-view').value=rd.content;
    renderEnvFields();
  } catch(e){}
}

function setEnvMode(m) {
  S.envMode=m;
  document.getElementById('mf').className='env-mode-btn'+(m==='fields'?' on':'');
  document.getElementById('mr').className='env-mode-btn'+(m==='raw'?' on':'');
  document.getElementById('env-fields-view').style.display=m==='fields'?'':'none';
  document.getElementById('env-raw-view').style.display=m==='raw'?'':'none';
}

function renderEnvFields() {
  const wrap=document.getElementById('env-fields-view');
  if(!S.envFields.length){wrap.innerHTML='<p style="color:var(--muted);padding:16px">No .env.example found.</p>';return;}
  let h='';
  S.envFields.forEach(sec=>{
    h+=`<div class="env-section"><div class="env-sec-title">${sec.name}</div>`;
    sec.fields.forEach(f=>{
      const aff=f.affects.map(a=>`<span class="aff-chip">${a}</span>`).join('');
      const type=f.secret?'password':'text';
      const val=(f.value||'').replace(/"/g,'&quot;');
      h+=`<div class="env-field">
        <div class="env-field-lbl">
          <span class="env-field-key">${f.key}</span>
          ${f.desc?`<span class="env-field-desc">${f.desc}</span>`:''}
        </div>
        <input class="env-field-input" type="${type}" data-key="${f.key}"
               value="${val}" placeholder="${f.default||''}"
               oninput="onFieldChange()">
        <div class="env-field-affects">${aff}</div>
      </div>`;
    });
    h+='</div>';
  });
  wrap.innerHTML=h;
}

function getFieldValues() {
  const vals={};
  document.querySelectorAll('.env-field-input').forEach(i=>{ vals[i.dataset.key]=i.value; });
  return vals;
}

function onFieldChange() {
  const vals=getFieldValues();
  // Rebuild what the env would look like and compare to original
  const changed=new Set();
  const orig={};
  S.envOrig.split('\n').forEach(line=>{
    const s=line.trim();
    if(s&&!s.startsWith('#')&&s.includes('=')){
      const k=s.split('=')[0].trim(); orig[k]=s.slice(k.length+1);
    }
  });
  Object.entries(vals).forEach(([k,v])=>{ if((orig[k]||'')!==v) changed.add(k); });
  const aff=new Set();
  changed.forEach(k=>(S.envDeps[k]||[]).forEach(s=>aff.add(s)));
  const banner=document.getElementById('rbanner');
  if(aff.size){
    banner.classList.add('on');
    document.getElementById('rbl').innerHTML=[...aff].map(s=>`<span class="rchip">${s}</span>`).join('');
  } else banner.classList.remove('on');
}

function onRawChange() { onFieldChange(); }

async function saveEnv() {
  if(S.envMode==='fields') {
    const d=await api('/api/env/fields',null,'POST',{fields:getFieldValues()});
    if(d.ok) toast('Saved .env','ok'); else toast('Save failed','err');
  } else {
    const content=document.getElementById('env-raw-view').value;
    const d=await api('/api/env',null,'POST',{content});
    if(d.ok){ S.envOrig=content; toast('Saved .env','ok'); } else toast('Save failed','err');
  }
  document.getElementById('rbanner').classList.remove('on');
  await loadEnv();
}

async function loadExample() {
  if(!confirm('Reset .env to .env.example defaults?')) return;
  const d=await fetch('/api/env/example').then(r=>r.json());
  document.getElementById('env-raw-view').value=d.content;
  S.envOrig=d.content;
  await api('/api/env',null,'POST',{content:d.content});
  await loadEnv();
  toast('Reset to defaults','ok');
}

// ── logs ──────────────────────────────────────────────────────────────────────
function populateLogSel() {
  const sel=document.getElementById('lsel');
  SVC_META.forEach(s=>{ const o=document.createElement('option');
    o.value=s.name; o.textContent=s.icon+' '+s.label; sel.appendChild(o); });
}

function openLogs(name) {
  nav('logs');
  document.getElementById('lsel').value=name;
  startLogs();
}

function startLogs() {
  const svc=document.getElementById('lsel').value;
  if(!svc) return;
  if(S.logEs){S.logEs.close();S.logEs=null;}
  clearLog();
  document.getElementById('lout').textContent=`Connecting to ${svc}…\n`;
  S.logEs=new EventSource(`/api/logs/${svc}`);
  S.logEs.onmessage=e=>appendLog(JSON.parse(e.data));
  S.logEs.onerror=()=>appendLog('[stream ended]');
}

function appendLog(line) {
  const out=document.getElementById('lout');
  const d=document.createElement('div');
  const lo=line.toLowerCase();
  if(/error|fatal|critical/.test(lo)) d.className='ll-err';
  else if(/warn/.test(lo)) d.className='ll-warn';
  else if(/info|started|ready|listening/.test(lo)) d.className='ll-ok';
  d.textContent=line; out.appendChild(d);
  if(out.children.length>2000) out.removeChild(out.firstChild);
  if(S.logFollow) out.scrollTop=out.scrollHeight;
}

function clearLog(){document.getElementById('lout').innerHTML='';}
function toggleFollow(){
  S.logFollow=!S.logFollow;
  document.getElementById('lfbtn').textContent=S.logFollow?'📌 Following':'⏸ Paused';
}

// ── toasts ────────────────────────────────────────────────────────────────────
function toast(msg, type='inf') {
  const icons={ok:'✅',err:'❌',inf:'ℹ️'};
  const el=document.createElement('div');
  el.className=`toast ${type}`;
  el.innerHTML=`<span>${icons[type]||'ℹ️'}</span><span>${msg}</span>`;
  document.getElementById('tc').appendChild(el);
  setTimeout(()=>el.remove(), 4500);
}

// ── fetch helper ──────────────────────────────────────────────────────────────
async function api(url, body, method='POST', data=body) {
  const opts={method,headers:{'Content-Type':'application/json'}};
  if(data!=null) opts.body=JSON.stringify(data);
  return fetch(url,opts).then(r=>r.json());
}
</script>
</body>
</html>"""

class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

if __name__ == "__main__":
    for arg in sys.argv[1:]:
        if arg.startswith("--port="): PORT=int(arg.split("=",1)[1])
        elif arg.startswith("--host="): HOST=arg.split("=",1)[1]
    print(f"AI Stack Dashboard → http://localhost:{PORT}")
    print(f"Stack: {STACK_DIR}")
    Server((HOST, PORT), Handler).serve_forever()
