#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sqlite3,sys
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlparse
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from query import query
PAGE='''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MANIEMENTS V5 — V0</title><style>body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:900px;margin:40px auto;padding:0 18px;background:#111;color:#eee}h1{font-size:1.55rem}.muted{color:#aaa}.card{background:#1c1c1c;border:1px solid #333;border-radius:12px;padding:18px;margin:16px 0}label{display:block;margin:10px 0 4px}input{font:inherit;padding:10px;width:100%;box-sizing:border-box;background:#0d0d0d;color:#fff;border:1px solid #444;border-radius:8px}button{font:inherit;margin-top:14px;padding:10px 16px;border:0;border-radius:8px;cursor:pointer}table{width:100%;border-collapse:collapse;margin-top:12px}th,td{text-align:left;padding:8px;border-bottom:1px solid #333}.good{color:#8ee28e}.warn{color:#ffd27a}.bad{color:#ff9b9b}code{word-break:break-all}</style></head><body><h1>MANIEMENTS V5 — cache exact V0</h1><p class="muted">Interroge le snapshot P1 actuellement calculé. Exemples : <code>J963</code>, <code>AQ2</code>, <code>T</code> ou <code>10</code>.</p><div class="card"><form id="f"><label>Nord</label><input id="north" value="42" autocomplete="off"><label>Sud</label><input id="south" value="653" autocomplete="off"><button>Interroger</button></form></div><div id="out"></div><script>const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));document.getElementById('f').addEventListener('submit',async e=>{e.preventDefault();const n=north.value,s=south.value,out=document.getElementById('out');out.innerHTML='<div class="card">Recherche…</div>';try{const r=await fetch('/api/query?north='+encodeURIComponent(n)+'&south='+encodeURIComponent(s)),j=await r.json();if(!r.ok)throw new Error(j.error||'Erreur');let cls=j.status==='EXACT'?'good':(['DEFERRED','ACTIVE','PENDING'].includes(j.status)?'warn':'bad');let x=`<div class="card"><h2 class="${cls}">${esc(j.status)}</h2><p>Nord <b>${esc(j.north||'')}</b> — Sud <b>${esc(j.south||'')}</b></p>`;if(j.status==='EXACT'){x+=`<p>state_id ${j.state_id} — mode ${esc(j.solver_mode)}</p><table><tr><th>Target</th><th>Probabilité exacte</th><th>%</th></tr>`;for(const c of j.curve)x+=`<tr><td>${c.target}</td><td>${esc(c.fraction)}</td><td>${Number(c.percent).toFixed(6)}%</td></tr>`;x+='</table>'}else if(j.status==='DEFERRED')x+=`<p>Calcul exact différé au target ${j.blocked_target} après le cap de ${j.target_cap_seconds}s.</p>`;else if(j.message)x+=`<p>${esc(j.message)}</p>`;if(j.worker_id!==undefined)x+=`<p>Worker ${String(j.worker_id).padStart(2,'0')}</p>`;x+='</div>';out.innerHTML=x}catch(err){out.innerHTML=`<div class="card bad">${esc(err.message)}</div>`}});</script></body></html>'''
class Handler(BaseHTTPRequestHandler):
    db_path:Path
    def send_bytes(self,status,body,ctype):
        self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        u=urlparse(self.path)
        if u.path=='/': self.send_bytes(200,PAGE.encode(),'text/html; charset=utf-8'); return
        if u.path=='/api/query':
            q=parse_qs(u.query); north=q.get('north',[''])[0]; south=q.get('south',[''])[0]
            try:
                c=sqlite3.connect(f"file:{self.db_path.resolve()}?mode=ro",uri=True)
                try:r=query(c,north,south)
                finally:c.close()
                self.send_bytes(200,json.dumps(r,ensure_ascii=False,sort_keys=True).encode(),'application/json; charset=utf-8')
            except Exception as e:self.send_bytes(400,json.dumps({'error':str(e)},ensure_ascii=False).encode(),'application/json; charset=utf-8')
            return
        self.send_bytes(404,b'Not found','text/plain; charset=utf-8')
    def log_message(self,fmt,*args): print(f"[http] {self.address_string()} {fmt%args}")
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--db',default=str(HERE/'maniements_v5_p1_v0.sqlite')); ap.add_argument('--host',default='127.0.0.1'); ap.add_argument('--port',type=int,default=8765); a=ap.parse_args(); Handler.db_path=Path(a.db)
    if not Handler.db_path.exists(): raise SystemExit(f"DB introuvable: {Handler.db_path}")
    srv=ThreadingHTTPServer((a.host,a.port),Handler); print(f"MANIEMENTS V5 V0: http://{a.host}:{a.port}")
    try:srv.serve_forever()
    except KeyboardInterrupt:pass
if __name__=='__main__':main()
