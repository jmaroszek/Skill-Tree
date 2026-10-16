"""EXPERIMENTAL, NOT A PRODUCTION TOOL: bulk re-rate every node's value, interest,
effort and time estimates in a side-by-side capture page.

This is a standalone developer script, not part of the app. Nothing imports it,
it has no tests, and it is not wired into the UI. It is kept in the repo because
it worked well for the October 2026 re-rating and might become an in-app review
feature if the user decides to build one. Until then, treat it as a prototype:
do not document it for users or depend on it.

    python tools/rerate.py            # then open http://127.0.0.1:8053

What it does:
  - Reads the production DB read-only (never writes to it). Done nodes are left out.
  - Shows each node's current ratings next to controls for the new ones, with
    time entered in days/weeks/months/years, a "Keep as is" and a "Drop" button,
    and the ratings reference ("i") panel.
  - Autosaves progress to reviews/rerate_state.json (gitignored), so it can be
    stopped and resumed.
  - Applying the result is a separate step it does not perform: a script has to
    read the state file and write through GraphManager.update_node (backing the
    DB up first and listing any Drop deletions for approval).
"""
import json
import os
import pathlib
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "reviews" / "rerate_state.json"
PORT = 8053
DB = pathlib.Path(os.environ["LOCALAPPDATA"]) / "Skill Tree" / "Data" / "skilltree.db"


def load_data():
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    sys.path.insert(0, str(ROOT))
    from skilltree.store.settings import DEFAULT_RATINGS_DEFINITIONS, DEFAULT_TIME_SETTINGS
    raw = con.execute("select value from Settings where key='TIME_SETTINGS'").fetchone()
    ts = {**DEFAULT_TIME_SETTINGS, **(json.loads(raw[0]) if raw else {})}
    settings = {"hw": ts["hours_per_week"], "hm": ts["hours_per_month"]}
    raw = con.execute("select value from Settings where key='RATINGS_DEFINITIONS'").fetchone()
    ratings = json.loads(raw[0]) if raw else DEFAULT_RATINGS_DEFINITIONS
    nodes = []
    # Done nodes are left out: re-rating finished work has no effect on ranking.
    for r in con.execute("select * from Nodes where status != 'Done'"):
        # Time the node does not own: containers, inherited mode, and habit
        # mode (derived from a duration x intensity form). Not editable here.
        time_locked = (r["time_mode"] in ("inherited", "habit")
                       or r["type"] in ("Goal", "Milestone"))
        flags = []
        if r["status"] == "Done":
            flags.append("Done")
        if r["dormant"]:
            flags.append("dormant")
        if r["value_mode"] == "inherited":
            flags.append("value inherited")
        if r["time_mode"] == "habit":
            flags.append("time from habit form (not editable here)")
        elif time_locked:
            flags.append("time inherited")
        nodes.append({
            "name": r["name"], "type": r["type"], "desc": r["description"] or "",
            "ctx": r["context"] or "Uncategorized", "sub": r["subcontext"] or "(no subcontext)",
            "flags": flags, "v": r["value"], "i": r["interest"], "e": r["difficulty"],
            "o": r["time_o"], "m": r["time_m"], "p": r["time_p"], "timeLocked": time_locked,
        })
    nodes.sort(key=lambda n: (n["ctx"] == "Uncategorized", n["ctx"].lower(),
                              n["sub"] == "(no subcontext)", n["sub"].lower(), n["name"].lower()))
    return {"settings": settings, "nodes": nodes, "ratings": ratings}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path == "/api/data":
            state = json.loads(STATE_PATH.read_text("utf-8")) if STATE_PATH.exists() else {}
            self._send(200, json.dumps({**load_data(), "state": state}), "application/json")
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        if self.path != "/api/state":
            return self._send(404, "not found", "text/plain")
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        json.loads(body)  # reject malformed input before it touches the file
        STATE_PATH.parent.mkdir(exist_ok=True)
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_bytes(body)
        os.replace(tmp, STATE_PATH)
        self._send(200, "ok", "text/plain")

    def log_message(self, *args):
        pass


PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>Re-rate</title>
<style>
:root{--bg:#1b1d22;--panel:#25282f;--line:#383c46;--text:#e6e8ec;--dim:#98a0ae;--acc:#5aa2ff;--chg:#f0b24a;--ok:#4cc38a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.4 system-ui,sans-serif;display:flex;height:100vh}
#side{width:300px;border-right:1px solid var(--line);overflow-y:auto;padding:12px;flex:none}
#main{flex:1;overflow-y:auto;padding:16px 24px}
h1{font-size:16px;margin:0 0 8px}
.ctx{margin-top:12px;font-weight:600;color:var(--dim);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.grp{display:flex;justify-content:space-between;padding:4px 8px;border-radius:4px;cursor:pointer}
.grp:hover{background:var(--panel)} .grp.sel{background:var(--acc);color:#001}
.grp .n{color:var(--dim)} .grp.sel .n{color:#001} .grp.done .n{color:var(--ok)}
.bar{height:6px;background:var(--panel);border-radius:3px;margin:6px 0 10px}
.bar>div{height:100%;background:var(--ok);border-radius:3px}
#tools{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;position:sticky;top:-16px;background:var(--bg);padding:8px 0;z-index:2}
input,select,button{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:4px;padding:4px 8px;font:inherit}
button{cursor:pointer} button:hover{border-color:var(--acc)}
button.drop.on{background:#e5534b;border-color:#e5534b;color:#fff}
button.on{background:var(--acc);color:#001;border-color:var(--acc)}
.card{max-width:640px;background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--line);border-radius:6px;padding:12px 14px;margin-bottom:12px}
.card.dropped{border-left-color:#e5534b}.card.dropped .scale,.card.dropped .trow,.card.dropped .point{opacity:.35}
.card.kept{border-left-color:var(--ok)} .card.changed{border-left-color:var(--chg)}
.head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}
.name{font-weight:600;font-size:15px}
.meta{color:var(--dim);font-size:12px}
.desc{color:var(--dim);font-size:12px;margin:4px 0 8px;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:900px}
.desc.open{white-space:normal}
.row{display:flex;align-items:center;gap:10px;margin:4px 0}
.lbl{width:70px;color:var(--dim)}
.cur{width:28px;text-align:center;font-weight:700;background:var(--bg);border-radius:4px;padding:2px 0}
.arrow{color:var(--dim)}
.scale button{width:30px;padding:3px 0;text-align:center}
.scale button.cur-mark{border-color:var(--dim)}
.scale button.on{background:var(--chg);border-color:var(--chg)}
.trow{display:grid;grid-template-columns:50px repeat(3,165px);gap:10px;margin-top:6px;align-items:start}
.tcell .curt{font-size:12px;color:var(--dim);margin-bottom:3px}
.tcell .curt b{color:var(--text)}
.tcell input{width:62px} .tcell select{width:88px} .tcell .h{font-size:11px;color:var(--chg);margin-top:2px;min-height:14px}
.point{font-size:12px;color:var(--dim);margin-top:6px}
.point b{color:var(--text)} .point .new{color:var(--chg)}
#ref{position:fixed;right:16px;top:16px;width:760px;max-width:calc(100vw - 32px);height:70vh;max-height:calc(100vh - 32px);min-width:360px;min-height:200px;background:var(--panel);border:1px solid var(--line);border-radius:6px;box-shadow:0 8px 30px #0008;display:none;flex-direction:column;z-index:10;resize:both;overflow:hidden}
#ref.open{display:flex}
#refhead{display:flex;align-items:center;padding:8px 10px;background:var(--bg);border-bottom:1px solid var(--line);cursor:move;user-select:none;font-weight:600}
#refbody{overflow:auto;flex:1;padding:4px}
#ref table{width:100%;border-collapse:collapse;font-size:12px}
#ref th{text-align:left;padding:6px;color:var(--dim);position:sticky;top:0;background:var(--panel);border-bottom:1px solid var(--line)}
#ref td{padding:6px;vertical-align:top;border-bottom:1px solid var(--line)}
#ref tr:nth-child(even) td{background:var(--bg)}
#ref td:first-child{font-weight:700;color:var(--dim);text-align:center;width:30px}
.ibtn{border-radius:50%;width:26px;height:26px;padding:0;font-weight:700;font-style:italic;font-family:serif}
.empty{color:var(--dim);padding:40px 0}
</style></head><body>
<div id="side"></div>
<div id="main">
 <div id="tools">
  <input id="search" placeholder="Search all nodes" style="width:220px">
  <span id="filters"></span>
  <button class="ibtn" id="refbtn" title="Ratings reference">i</button>
  <span id="saved" class="meta" style="margin-left:auto;align-self:center"></span>
 </div>
 <div id="list"></div>
</div>
<div id="ref"><div id="refhead"><span>Ratings Reference</span><button id="refclose" style="margin-left:auto">×</button></div><div id="refbody"></div></div>
<script>
let NODES=[], S={}, SET={}, sel=null, filter='all', q='';
const $=s=>document.querySelector(s);
const UNITS=['hours','days','weeks','months','years'];
const mult=u=>({hours:1,days:SET.hw/7,weeks:SET.hw,months:SET.hm,years:13*SET.hm})[u];
function friendly(h){ // mirrors format_time_friendly
  if(!h||h<=0) return '0h';
  const t=[[13*SET.hm,'y'],[SET.hm,'m'],[SET.hw,'w'],[SET.hw/7,'d']];
  for(const [s,x] of t) if(s>0&&h>=s){const a=Math.round(h/s*10)/10;return a+x}
  return Math.round(h*10)/10+'h';
}
function bigUnit(h){
  const t=[[13*SET.hm,'years'],[SET.hm,'months'],[SET.hw,'weeks'],[SET.hw/7,'days']];
  for(const [s,x] of t) if(s>0&&h>=s) return x; return 'hours';
}
function point(o,m,p){ // mirrors models.expected_time_estimate
  o=o||0;m=m||0;p=p||0;
  if(m>0&&o==0&&p==0) return m;
  if(m==0&&o>0&&p>0) m=Math.sqrt(o*p);
  if(!o&&!m&&!p) return 1;
  if(o<=0)o=.1; if(m<o)m=o; if(p<m)p=m;
  return Math.round((.3*o+.4*m+.3*p)*100)/100;
}
const key=n=>n.ctx+' / '+n.sub;
function st(n){return S[n.name]||(S[n.name]={})}
function hoursOf(t){return t&&t.n!==''&&t.n!=null&&!isNaN(+t.n)?+t.n*mult(t.u):null}
function isChanged(s){return ['v','i','e'].some(k=>s[k]!=null)||['o','m','p'].some(k=>hoursOf(s[k])!=null)}
function status(n){const s=S[n.name]||{};return s.drop?'dropped':isChanged(s)?'changed':s.kept?'kept':'new'}
let tm;function save(){
  $('#saved').textContent='saving…';clearTimeout(tm);
  tm=setTimeout(async()=>{
    const out={};for(const k in S){const s=S[k];if(isChanged(s)||s.kept||s.drop)out[k]=s}
    await fetch('/api/state',{method:'POST',body:JSON.stringify(out)});
    $('#saved').textContent='saved';renderSide();
  },300);
}
function renderSide(){
  const groups={};
  NODES.forEach(n=>{(groups[key(n)]=groups[key(n)]||{ctx:n.ctx,sub:n.sub,t:0,d:0}).t++;
    if(status(n)!='new')groups[key(n)].d++});
  const tot=NODES.length,done=NODES.filter(n=>status(n)!='new').length,chg=NODES.filter(n=>status(n)=='changed').length,drp=NODES.filter(n=>status(n)=='dropped').length;
  let h=`<h1>Re-rate</h1><div class="meta">${done}/${tot} reviewed · ${chg} changed · ${drp} dropped</div><div class="bar"><div style="width:${done/tot*100}%"></div></div>`;
  let last=null;
  for(const g of Object.values(groups)){
    if(g.ctx!=last){h+=`<div class="ctx">${g.ctx}</div>`;last=g.ctx}
    h+=`<div class="grp ${sel==g.ctx+' / '+g.sub?'sel':''} ${g.d==g.t?'done':''}" data-k="${g.ctx} / ${g.sub}"><span>${g.sub}</span><span class="n">${g.d}/${g.t}</span></div>`;
  }
  $('#side').innerHTML=h;
  document.querySelectorAll('.grp').forEach(e=>e.onclick=()=>{sel=e.dataset.k;q='';$('#search').value='';renderList();renderSide();$('#main').scrollTop=0});
}
function renderFilters(){
  $('#filters').innerHTML=[['all','All'],['new','To review'],['kept','Kept'],['changed','Changed'],['dropped','Dropped']]
   .map(([k,l])=>`<button data-f="${k}" class="${filter==k?'on':''}">${l}</button>`).join(' ');
  document.querySelectorAll('[data-f]').forEach(b=>b.onclick=()=>{filter=b.dataset.f;renderFilters();renderList()});
}
function esc(s){return s.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[c])}
function renderList(){
  const ql=q.toLowerCase();
  const items=NODES.map((n,ix)=>[n,ix]).filter(([n])=>(ql?n.name.toLowerCase().includes(ql):key(n)==sel)&&(filter=='all'||status(n)==filter));
  const list=$('#list');
  if(!items.length){list.innerHTML='<div class="empty">Nothing here.</div>';return}
  list.innerHTML='';
  let lastKey=null;
  for(const [n,ix] of items){
    if(ql&&key(n)!=lastKey){const h=document.createElement('div');h.className='ctx';h.textContent=key(n);list.appendChild(h);lastKey=key(n)}
    list.appendChild(card(n,ix));
  }
}
function card(n,ix){
  const s=st(n),el=document.createElement('div');el.className='card';el.dataset.ix=ix;
  const scale=(f,label)=>`<div class="row"><span class="lbl">${label}</span><span class="cur">${n[f]}</span><span class="arrow">→</span><span class="scale">`+
    Array.from({length:10},(_,i)=>`<button data-f="${f}" data-v="${i+1}">${i+1}</button>`).join('')+`</span></div>`;
  let t='';
  if(n.timeLocked) t=`<div class="meta" style="margin-top:6px">Time: not editable here (${n.flags.filter(f=>f.startsWith('time')).join('')})</div>`;
  else t=`<div class="trow"><span class="lbl">Time</span>`+[['o','Lower'],['m','Expected'],['p','Upper']].map(([f,l])=>
    `<div class="tcell"><div class="curt">${l}: <b>${friendly(n[f])}</b> <span>(${+n[f].toFixed(2)}h)</span></div>
     <input type="number" min="0" step="any" data-t="${f}" placeholder="new"> <select data-u="${f}">${UNITS.map(u=>`<option>${u}</option>`).join('')}</select>
     <div class="h" data-h="${f}"></div></div>`).join('')+`</div><div class="point" data-point></div>`;
  el.innerHTML=`<div class="head"><div><span class="name">${esc(n.name)}</span> <span class="meta">${n.type}${n.flags.length?' · '+n.flags.join(' · '):''}</span></div>
    <span><button data-keep>Keep as is</button> <button class="drop" data-drop title="Delete this node when the migration runs">Drop</button></span></div>
    ${n.desc?`<div class="desc">${esc(n.desc)}</div>`:''}
    ${scale('v','Value')}${scale('i','Interest')}${scale('e','Effort')}${t}`;
  el.querySelector('.desc')&&(el.querySelector('.desc').onclick=e=>e.target.classList.toggle('open'));
  el.querySelectorAll('.scale button').forEach(b=>b.onclick=()=>{
    const f=b.dataset.f,v=+b.dataset.v;s[f]=s[f]===v?undefined:v;if(s[f]==null)delete s[f];else{delete s.kept;delete s.drop};refresh(el,n);save()});
  el.querySelector('[data-keep]').onclick=()=>{
    if(s.kept&&!isChanged(s)){delete s.kept}else{for(const k of ['v','i','e','o','m','p'])delete s[k];delete s.drop;s.kept=true;
      el.querySelectorAll('[data-t]').forEach(i=>i.value='')}
    refresh(el,n);save()};
  el.querySelector('[data-drop]').onclick=()=>{
    if(s.drop){delete s.drop}else{for(const k of ['v','i','e','o','m','p'])delete s[k];delete s.kept;s.drop=true;
      el.querySelectorAll('[data-t]').forEach(i=>i.value='')}
    refresh(el,n);save()};
  el.querySelectorAll('[data-t]').forEach(i=>{
    const f=i.dataset.t,sl=el.querySelector(`[data-u="${f}"]`);
    const t0=s[f];sl.value=t0?t0.u:bigUnit(n[f]);if(t0)i.value=t0.n;
    const upd=()=>{if(i.value==='')delete s[f];else{s[f]={n:i.value,u:sl.value};delete s.kept;delete s.drop}refresh(el,n);save()};
    i.oninput=upd;sl.onchange=()=>{if(i.value!=='')upd();else refresh(el,n)};
  });
  refresh(el,n);return el;
}
function refresh(el,n){
  const s=st(n),stt=status(n);el.className='card '+(stt=='new'?'':stt);
  el.querySelectorAll('.scale button').forEach(b=>{const f=b.dataset.f,v=+b.dataset.v;
    b.classList.toggle('on',s[f]===v);b.classList.toggle('cur-mark',n[f]===v)});
  const k=el.querySelector('[data-keep]');k.classList.toggle('on',stt=='kept');k.textContent=stt=='kept'?'Kept ✓':'Keep as is';
  const dr=el.querySelector('[data-drop]');dr.classList.toggle('on',stt=='dropped');dr.textContent=stt=='dropped'?'Dropped ✕':'Drop';
  if(n.timeLocked) return;
  const nh={};
  for(const f of ['o','m','p']){
    const h=hoursOf(s[f]);nh[f]=h;
    el.querySelector(`[data-h="${f}"]`).textContent=h==null?'':`= ${+h.toFixed(2)}h (${friendly(h)})`;
  }
  const merged=['o','m','p'].map(f=>nh[f]!=null?nh[f]:n[f]);
  const cur=point(n.o,n.m,n.p),nw=point(...merged);
  const anyT=['o','m','p'].some(f=>nh[f]!=null);
  el.querySelector('[data-point]').innerHTML=`Resolved estimate: <b>${friendly(cur)}</b> (${cur}h)`+(anyT?` → <span class="new"><b>${friendly(nw)}</b> (${nw}h)</span>`:'');
}
function initRef(rows){
  const b=t=>{const i=t.indexOf(':');return i<0?esc(t):'<b>'+esc(t.slice(0,i+1))+'</b>'+esc(t.slice(i+1))};
  $('#refbody').innerHTML='<table><thead><tr><th>#</th><th>Value</th><th>Interest</th><th>Effort</th></tr></thead><tbody>'+
    rows.map(d=>`<tr><td>${d.rating}</td><td>${b(d.value)}</td><td>${b(d.interest)}</td><td>${b(d.effort)}</td></tr>`).join('')+'</tbody></table>';
  const ref=$('#ref');
  $('#refbtn').onclick=()=>ref.classList.toggle('open');
  $('#refclose').onclick=()=>ref.classList.remove('open');
  $('#refhead').onmousedown=e=>{
    if(e.target.id=='refclose')return;
    const r=ref.getBoundingClientRect(),dx=e.clientX-r.left,dy=e.clientY-r.top;
    ref.style.right='auto';ref.style.left=r.left+'px';ref.style.top=r.top+'px';
    const mv=ev=>{ref.style.left=Math.max(0,ev.clientX-dx)+'px';ref.style.top=Math.max(0,ev.clientY-dy)+'px'};
    const up=()=>{removeEventListener('mousemove',mv);removeEventListener('mouseup',up)};
    addEventListener('mousemove',mv);addEventListener('mouseup',up);
  };
}
async function init(){
  const d=await (await fetch('/api/data')).json();
  NODES=d.nodes;SET=d.settings;initRef(d.ratings);S=d.state||{};
  sel=key(NODES[0]);
  $('#search').oninput=e=>{q=e.target.value;renderList()};
  renderFilters();renderSide();renderList();
}
init();
</script></body></html>
"""

if __name__ == "__main__":
    load_data()  # fail fast if the DB is unreadable
    print(f"Re-rate tool on http://127.0.0.1:{PORT}  (Ctrl+C to stop)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
