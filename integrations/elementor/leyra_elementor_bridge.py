#!/usr/bin/env python3
"""LEYRA Elementor Bridge: dependency-free, authenticated WordPress MCP proxy."""
import os, json, base64, hmac, re, ssl
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote

VERSION = "1.0.0"
TOKEN = os.getenv("LEYRA_BRIDGE_TOKEN", "")
WP_URL = os.getenv("LEYRA_WP_URL", "").rstrip("/")
WP_USER = os.getenv("LEYRA_WP_USER", "")
WP_PASSWORD = os.getenv("LEYRA_WP_APP_PASSWORD", "").replace(" ", "")
HOST = os.getenv("LEYRA_BRIDGE_HOST", "127.0.0.1")
PORT = int(os.getenv("LEYRA_BRIDGE_PORT", "8011"))
TIMEOUT = min(max(int(os.getenv("LEYRA_BRIDGE_TIMEOUT", "20")), 3), 60)
ALLOW_WRITES = os.getenv("LEYRA_ELEMENTOR_ALLOW_MUTATIONS", "false").lower() == "true"
TOOLS = {x.strip() for x in os.getenv("LEYRA_ELEMENTOR_ALLOWED_TOOLS", "").split(",") if x.strip()}
RESOURCES = {x.strip() for x in os.getenv("LEYRA_ELEMENTOR_ALLOWED_RESOURCES", "").split(",") if x.strip()}
TOOL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")

def config_error():
    if len(TOKEN) < 32: return "LEYRA_BRIDGE_TOKEN must contain at least 32 characters"
    if not all((WP_URL, WP_USER, WP_PASSWORD)): return "Set LEYRA_WP_URL, LEYRA_WP_USER and LEYRA_WP_APP_PASSWORD"
    u = urlparse(WP_URL)
    if u.scheme not in ("https", "http") or not u.netloc or u.username or u.password: return "Invalid LEYRA_WP_URL"
    if u.scheme != "https" and u.hostname not in ("localhost", "127.0.0.1"): return "Remote WordPress requires HTTPS"
    return None

def upstream(method, params):
    url = WP_URL + "/wp-json/elementor/v1/mcp-proxy"
    body = None
    if method == "GET": url += "?uri=" + quote(params["uri"], safe=":/#")
    else: body = json.dumps({"tool": params["tool"], "input": params.get("input", {})}).encode()
    auth = base64.b64encode((WP_USER + ":" + WP_PASSWORD).encode()).decode()
    req = Request(url, data=body, method=method, headers={"Authorization":"Basic "+auth,
        "Accept":"application/json", "Content-Type":"application/json", "User-Agent":"LEYRA-Elementor-Bridge/1.0"})
    try:
        with urlopen(req, timeout=TIMEOUT, context=ssl.create_default_context()) as r:
            raw = r.read(2_000_000)
            try: return r.status, json.loads(raw.decode())
            except Exception: return r.status, {"raw":raw.decode("utf-8","replace")[:4000]}
    except HTTPError as e:
        raw=e.read(50000).decode("utf-8","replace")
        try: data=json.loads(raw)
        except Exception: data={"error":"wordpress_http_error","detail":raw[:1200]}
        return e.code,data
    except (URLError, TimeoutError, OSError) as e:
        return 502,{"error":"wordpress_unreachable","detail":str(e)[:400]}

class Handler(BaseHTTPRequestHandler):
    server_version = "LEYRA-Elementor-Bridge/"+VERSION
    def log_message(self, fmt, *args): print("[LEYRA-BRIDGE] "+(fmt % args))
    def reply(self, code, obj):
        raw=json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff"); self.end_headers(); self.wfile.write(raw)
    def authorized(self):
        return bool(TOKEN) and hmac.compare_digest(self.headers.get("Authorization",""),"Bearer "+TOKEN)
    def do_GET(self):
        parsed=urlparse(self.path)
        if parsed.path=="/health": return self.reply(200,{"ok":True,"service":"LEYRA Elementor Bridge","version":VERSION})
        if not self.authorized(): return self.reply(401,{"error":"unauthorized"})
        if parsed.path=="/leyra/elementor/status":
            err=config_error()
            return self.reply(200 if not err else 503,{"ok":not bool(err),"version":VERSION,
                "endpoint":"/wp-json/elementor/v1/mcp-proxy","mutations_enabled":ALLOW_WRITES,
                "allowed_tools":len(TOOLS),"configuration_error":err})
        if parsed.path=="/leyra/elementor/resource":
            if (err:=config_error()): return self.reply(503,{"error":"not_configured","detail":err})
            uri=parse_qs(parsed.query).get("uri",[""])[0]
            if not uri or len(uri)>500 or "\n" in uri: return self.reply(400,{"error":"invalid_uri"})
            if RESOURCES and uri not in RESOURCES: return self.reply(403,{"error":"resource_not_allowed"})
            code,data=upstream("GET",{"uri":uri}); return self.reply(code,{"ok":code<400,"upstream":data})
        return self.reply(404,{"error":"not_found"})
    def do_POST(self):
        if not self.authorized(): return self.reply(401,{"error":"unauthorized"})
        if urlparse(self.path).path!="/leyra/elementor/tool": return self.reply(404,{"error":"not_found"})
        if (err:=config_error()): return self.reply(503,{"error":"not_configured","detail":err})
        try:
            size=int(self.headers.get("Content-Length","0"))
            if size<2 or size>256000: return self.reply(413,{"error":"invalid_body_size"})
            data=json.loads(self.rfile.read(size).decode())
        except Exception: return self.reply(400,{"error":"invalid_json"})
        tool=data.get("tool") if isinstance(data,dict) else None
        args=data.get("input",{}) if isinstance(data,dict) else None
        if not isinstance(tool,str) or not TOOL_RE.fullmatch(tool) or not isinstance(args,dict):
            return self.reply(400,{"error":"invalid_tool_or_input"})
        if not TOOLS or tool not in TOOLS: return self.reply(403,{"error":"tool_not_allowlisted"})
        if not ALLOW_WRITES and re.search(r"(create|update|delete|remove|publish|manage|build|reorder|import|export)",tool,re.I):
            return self.reply(403,{"error":"mutations_disabled"})
        code,result=upstream("POST",{"tool":tool,"input":args})
        return self.reply(code,{"ok":code<400,"tool":tool,"upstream":result})

def main():
    err=config_error()
    if err: raise SystemExit("CONFIGURATION ERROR: "+err)
    if HOST not in ("127.0.0.1","localhost") and not HOST.startswith("192.168."):
        raise SystemExit("Bind only to localhost or private 192.168.x.x LAN")
    server=ThreadingHTTPServer((HOST,PORT),Handler)
    print(f"LEYRA Elementor Bridge {VERSION} listening on http://{HOST}:{PORT}")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__=="__main__": main()
