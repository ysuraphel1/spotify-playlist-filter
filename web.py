#!/usr/bin/env python3
"""
Graduation Playlist Web Builder
pip3 install flask
python3 ~/graduation_web.py  →  opens http://localhost:5001
"""

import os, time, webbrowser, statistics
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

CLIENT_ID     = os.getenv("SPOTIFY_CLIENT_ID",     "your_client_id")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "your_client_secret")
REDIRECT_URI  = os.getenv("SPOTIFY_REDIRECT_URI",  "http://127.0.0.1:3000/callback")
CACHE_PATH    = os.path.expanduser("~/.graduation_spotify_cache")
SOURCE_URL    = os.getenv("SPOTIFY_SOURCE_URL",     "https://open.spotify.com/playlist/your_source_playlist")
TARGET_URL    = os.getenv("SPOTIFY_TARGET_URL",     "https://open.spotify.com/playlist/your_target_playlist")
SCOPE = ("playlist-read-private playlist-read-collaborative "
         "playlist-modify-public playlist-modify-private")

# ── Genre signal weights (+ve = energetic/happy, -ve = chill/sad) ────────────
# Energy: positive = high energy, negative = low energy
ENERGY_W = {
    "drill": 3, "trap": 3, "dancehall": 3, "reggaeton": 3, "afrobeats": 3,
    "dance pop": 2.5, "edm": 2.5, "house": 2.5, "techno": 2.5, "trance": 2.5,
    "drum and bass": 2.5, "grime": 2.5, "club": 2.5,
    "hip hop": 2, "rap": 2, "hip-hop": 2, "disco": 2, "funk": 2,
    "dance": 1.5, "r&b": 1.5, "rnb": 1.5, "electronic": 1.5,
    "pop": 1, "indie pop": 1, "electropop": 1, "synth pop": 1, "alt pop": 1,
    "alternative": 0.5, "indie": 0.5, "rock": 0.5,
    "neo soul": -0.5, "soul": -0.3,
    "dream pop": -1, "shoegaze": -1, "lo-fi": -1.5, "chillwave": -1,
    "acoustic": -2, "folk": -2, "ballad": -2,
    "jazz": -2, "classical": -3, "ambient": -3, "sleep": -3,
}
# Mood: positive = happy/upbeat, negative = melancholic/dark
MOOD_W = {
    "disco": 3, "funk": 3, "dance pop": 2.5, "party": 2.5, "bubblegum": 2.5,
    "feel good": 2, "upbeat": 2, "happy": 2, "summer": 2, "tropical": 2,
    "pop": 1.5, "dancehall": 1.5, "afrobeats": 1.5, "reggaeton": 1.5,
    "hip hop": 1, "rap": 1, "r&b": 0.5, "indie pop": 0.5,
    "alternative": -0.5, "indie": -0.5, "neo soul": -0.5,
    "melancholic": -2, "sad": -2, "heartbreak": -2, "emo": -2,
    "post-punk": -1.5, "dark wave": -2, "gothic": -2, "goth": -2,
    "doom": -2.5, "depressive": -3, "grunge": -1,
}

def raw_score(genres, popularity, duration_ms):
    g = " ".join(genres).lower()
    e_raw = sum(w for k, w in ENERGY_W.items() if k in g)
    m_raw = sum(w for k, w in MOOD_W.items()   if k in g)
    # duration signal: tracks under 3.5 min skew energetic
    dur_min = duration_ms / 60000
    dur_signal = max(0, (3.5 - dur_min) * 0.15)   # +0 to +0.5ish
    return e_raw + (popularity / 100) * 2 + dur_signal, m_raw + (popularity / 100) * 0.5


def normalize(values):
    """Map a list of raw scores onto 0-1 using min-max with 5th/95th percentile clipping."""
    if len(values) < 2:
        return [0.5] * len(values)
    lo, hi = sorted(values)[max(0, int(len(values)*0.05))], \
             sorted(values)[min(len(values)-1, int(len(values)*0.95))]
    span = hi - lo or 1
    return [round(min(max((v - lo) / span, 0), 1), 3) for v in values]

def sp():
    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI, scope=SCOPE, cache_path=CACHE_PATH))

_cache = None

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/tracks")
def api_tracks():
    global _cache
    if _cache:
        return jsonify(_cache)
    s = sp()
    pid = SOURCE_URL.split("/")[-1].split("?")[0]
    raw, page = [], s.playlist_items(pid)
    raw.extend(page["items"])
    while page.get("next"):
        page = s.next(page); raw.extend(page["items"])

    tracks, aids = [], set()
    for item in raw:
        t = item.get("track") or item.get("item")
        if not t or item.get("is_local") or t.get("is_local"): continue
        if t.get("type") != "track" or t.get("explicit"):       continue
        tracks.append(t)
        for a in t["artists"]:
            if a.get("id"): aids.add(a["id"])

    ag = {}
    for i in range(0, len(list(aids)), 50):
        try:
            res = s.artists(list(aids)[i:i+50])
            for a in res["artists"]:
                if a: ag[a["id"]] = a.get("genres", [])
        except Exception: pass
        time.sleep(0.1)

    seen, rows, e_raws, m_raws = set(), [], [], []
    for t in tracks:
        if t["id"] in seen: continue
        seen.add(t["id"])
        genres = []
        for a in t["artists"]: genres.extend(ag.get(a["id"], []))
        er, mr = raw_score(genres, t.get("popularity", 50), t.get("duration_ms", 210000))
        e_raws.append(er); m_raws.append(mr)
        img = t["album"]["images"][-1]["url"] if t["album"].get("images") else None
        rows.append({
            "id": t["id"], "name": t["name"],
            "artist": ", ".join(a["name"] for a in t["artists"]),
            "image": img, "preview_url": t.get("preview_url"),
            "popularity": t.get("popularity", 50),
            "year": int(t["album"]["release_date"][:4]) if t["album"].get("release_date") else 2000,
        })

    # Normalize scores across the whole playlist so the full 0-1 range is used
    e_norm = normalize(e_raws)
    m_norm = normalize(m_raws)
    out = []
    for row, e, m in zip(rows, e_norm, m_norm):
        out.append({**row, "energy": e, "mood": m})

    out.sort(key=lambda x: x["energy"] + x["mood"], reverse=True)
    _cache = out
    return jsonify(out)

@app.route("/api/save", methods=["POST"])
def api_save():
    ids = request.json.get("track_ids", [])
    if not ids: return jsonify({"error":"no tracks"}), 400
    s = sp()
    tid = TARGET_URL.split("/")[-1].split("?")[0]
    s.playlist_replace_items(tid, [])
    for i in range(0, len(ids), 100):
        s.playlist_add_items(tid, ids[i:i+100])
    s.playlist_change_details(tid, description=f"Graduation playlist — {len(ids)} songs.")
    return jsonify({"success": True, "count": len(ids)})

# ── HTML ──────────────────────────────────────────────────────────────────────
HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>🎓 Graduation Playlist Builder</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#080812;--surf:#111120;--surf2:#1a1a2e;--brd:rgba(255,255,255,.07);
  --p1:#8B5CF6;--p2:#3B82F6;--gold:#F59E0B;--org:#F97316;
  --txt:#eeeef8;--dim:rgba(238,238,248,.42);--r:12px;
}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
  background:var(--bg);color:var(--txt);min-height:100vh}

/* header */
.hdr{padding:24px 40px;border-bottom:1px solid var(--brd);
  display:flex;align-items:center;gap:16px}
.hdr-title{font-size:21px;font-weight:700;
  background:linear-gradient(135deg,var(--gold),var(--org));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hdr-sub{color:var(--dim);font-size:12px;margin-top:3px}

/* layout */
.wrap{max-width:1280px;margin:0 auto;padding:28px 40px;
  display:grid;grid-template-columns:310px 1fr;gap:24px;align-items:start}

/* controls */
.ctrl{position:sticky;top:20px;background:var(--surf);border:1px solid var(--brd);
  border-radius:var(--r);padding:20px;display:flex;flex-direction:column;gap:20px}
.lbl{font-size:10px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;
  color:var(--dim);margin-bottom:9px}

/* presets */
.pills{display:flex;flex-wrap:wrap;gap:6px}
.pill{padding:6px 12px;border-radius:20px;border:1px solid var(--brd);
  background:0;color:var(--dim);font-size:12px;cursor:pointer;
  transition:all .15s;font-family:inherit}
.pill:hover{border-color:rgba(255,255,255,.18);color:var(--txt)}
.pill.on{background:linear-gradient(135deg,var(--p1),var(--p2));
  border-color:transparent;color:#fff;font-weight:600}

/* sliders */
.sls{display:flex;flex-direction:column;gap:16px}
.sl{display:flex;flex-direction:column;gap:6px}
.sl-hd{display:flex;justify-content:space-between;align-items:baseline}
.sl-name{font-size:13px;font-weight:500}
.sl-v{font-size:12px;color:var(--dim);font-variant-numeric:tabular-nums}
input[type=range]{-webkit-appearance:none;width:100%;height:4px;border-radius:2px;
  outline:0;cursor:pointer;
  background:linear-gradient(to right,var(--p1) var(--pct,0%),var(--surf2) var(--pct,0%))}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;
  width:16px;height:16px;border-radius:50%;background:#fff;
  box-shadow:0 1px 5px rgba(0,0,0,.6);transition:transform .1s}
input[type=range]::-webkit-slider-thumb:hover{transform:scale(1.2)}
.sl-ends{display:flex;justify-content:space-between;font-size:10px;color:var(--dim);margin-top:1px}

/* CTA */
.cta{background:var(--surf2);border-radius:10px;padding:15px}
.big{font-size:34px;font-weight:800;line-height:1;
  background:linear-gradient(135deg,var(--gold),var(--org));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}
.big-lbl{font-size:12px;color:var(--dim);margin-top:4px;margin-bottom:13px}
.save{width:100%;padding:11px;border-radius:9px;border:0;
  background:linear-gradient(135deg,var(--p1),var(--p2));
  color:#fff;font-size:13px;font-weight:600;cursor:pointer;
  transition:all .18s;font-family:inherit}
.save:hover:not(:disabled){opacity:.87;transform:translateY(-1px)}
.save:disabled{opacity:.3;cursor:not-allowed;transform:none}

/* panel */
.panel{display:flex;flex-direction:column;gap:12px}
.ph{display:flex;align-items:center;justify-content:space-between}
.tally{font-size:12px;color:var(--dim)}
.srch{background:var(--surf);border:1px solid var(--brd);border-radius:8px;
  padding:7px 12px;color:var(--txt);font-size:12px;outline:0;
  font-family:inherit;width:190px}
.srch::placeholder{color:var(--dim)}
.srch:focus{border-color:rgba(255,255,255,.18)}

/* loading */
.ld{display:flex;flex-direction:column;align-items:center;
  justify-content:center;padding:80px;gap:13px;color:var(--dim)}
.spin{width:32px;height:32px;border:3px solid var(--surf2);
  border-top-color:var(--p1);border-radius:50%;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

/* rows */
.list{display:flex;flex-direction:column;gap:2px}
.row{display:grid;grid-template-columns:44px 1fr 88px;gap:10px;
  align-items:center;padding:8px 10px;border-radius:8px;
  cursor:pointer;transition:background .1s,opacity .15s;user-select:none}
.row:hover{background:var(--surf)}
.row.off{opacity:.18}
.art{width:44px;height:44px;border-radius:5px;object-fit:cover;background:var(--surf2)}
.art-ph{width:44px;height:44px;border-radius:5px;background:var(--surf2);
  display:flex;align-items:center;justify-content:center;font-size:16px}
.info{min-width:0}
.tn{font-size:13px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.an{font-size:11px;color:var(--dim);margin-top:2px;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.bars{display:flex;flex-direction:column;gap:5px}
.br{display:flex;align-items:center;gap:5px;font-size:10px}
.bl{width:14px;text-align:center;color:var(--dim)}
.bg{flex:1;height:3px;background:var(--surf2);border-radius:2px;overflow:hidden}
.bf{height:100%;border-radius:2px;
  background:linear-gradient(to right,var(--p1),var(--p2))}

/* toast */
.toast{position:fixed;bottom:26px;left:50%;
  transform:translateX(-50%) translateY(70px);
  background:#22c55e;color:#fff;padding:10px 20px;
  border-radius:9px;font-size:13px;font-weight:500;
  transition:transform .28s;z-index:999;white-space:nowrap}
.toast.up{transform:translateX(-50%) translateY(0)}

@media(max-width:740px){
  .wrap{grid-template-columns:1fr;padding:16px}
  .ctrl{position:static}
  .hdr{padding:18px 16px}
}
</style>
</head>
<body>

<header class="hdr">
  <div style="font-size:30px">🎓</div>
  <div>
    <div class="hdr-title">Graduation Playlist Builder</div>
    <div class="hdr-sub" id="sub">Loading tracks…</div>
  </div>
</header>

<div class="wrap">
  <aside class="ctrl">

    <div>
      <div class="lbl">Vibe Preset</div>
      <div class="pills">
        <button class="pill"    data-e="40" data-m="45" onclick="preset(this)">🎓 Ceremony</button>
        <button class="pill on" data-e="55" data-m="50" onclick="preset(this)">🎉 Celebration</button>
        <button class="pill"    data-e="72" data-m="50" onclick="preset(this)">🔥 Bangers</button>
        <button class="pill"    data-e="20" data-m="30" onclick="preset(this)">🥹 Nostalgic</button>
        <button class="pill"    data-e="0"  data-m="0"  onclick="preset(this)">✨ All Clean</button>
      </div>
    </div>

    <div class="sls">
      <div class="lbl">Fine-tune</div>
      <div class="sl">
        <div class="sl-hd">
          <span class="sl-name">⚡ Energy</span>
          <span class="sl-v" id="ev">55%+</span>
        </div>
        <input type="range" id="esl" min="0" max="100" value="55" oninput="slide()">
        <div class="sl-ends"><span>Chill</span><span>Hype</span></div>
      </div>
      <div class="sl">
        <div class="sl-hd">
          <span class="sl-name">😊 Mood</span>
          <span class="sl-v" id="mv">50%+</span>
        </div>
        <input type="range" id="msl" min="0" max="100" value="50" oninput="slide()">
        <div class="sl-ends"><span>Melancholic</span><span>Euphoric</span></div>
      </div>
    </div>

    <div class="cta">
      <div class="big" id="cnt">—</div>
      <div class="big-lbl">songs match your vibe</div>
      <button class="save" id="savebtn" onclick="doSave()" disabled>
        Save to Graduation Playlist
      </button>
    </div>

  </aside>

  <main class="panel">
    <div class="ph">
      <div class="tally" id="tally"></div>
      <input class="srch" type="text" placeholder="🔍  Search…" id="q" oninput="render()">
    </div>
    <div id="box">
      <div class="ld"><div class="spin"></div>
        <div>Scoring your tracks…</div>
        <div style="font-size:11px;margin-top:2px">~15 s the first time</div>
      </div>
    </div>
  </main>
</div>

<div class="toast" id="toast"></div>

<script>
let tracks=[], flipped=new Set();

async function init(){
  const r=await fetch('/api/tracks');
  tracks=await r.json();
  document.getElementById('sub').textContent=tracks.length+' clean tracks ready';
  setSl(document.getElementById('esl'));
  setSl(document.getElementById('msl'));
  render();
}

function preset(btn){
  document.querySelectorAll('.pill').forEach(b=>b.classList.remove('on'));
  btn.classList.add('on');
  document.getElementById('esl').value=btn.dataset.e;
  document.getElementById('msl').value=btn.dataset.m;
  flipped.clear();
  slide(false);
}

function slide(clr=true){
  if(clr){document.querySelectorAll('.pill').forEach(b=>b.classList.remove('on'));flipped.clear();}
  const e=document.getElementById('esl'),m=document.getElementById('msl');
  document.getElementById('ev').textContent=e.value+'%+';
  document.getElementById('mv').textContent=m.value+'%+';
  setSl(e);setSl(m);render();
}

function setSl(el){el.style.setProperty('--pct',el.value+'%');}

function passes(t){
  return t.energy>=document.getElementById('esl').value/100 &&
         t.mood  >=document.getElementById('msl').value/100;
}
function isOn(t){
  if(flipped.has(t.id)) return !passes(t);
  return passes(t);
}
function toggle(id){flipped.has(id)?flipped.delete(id):flipped.add(id);render();}

function render(){
  if(!tracks.length) return;
  const q=document.getElementById('q').value.toLowerCase();
  const vis=q?tracks.filter(t=>t.name.toLowerCase().includes(q)||t.artist.toLowerCase().includes(q)):tracks;
  const onCnt=tracks.filter(t=>isOn(t)).length;
  document.getElementById('cnt').textContent=onCnt;
  document.getElementById('savebtn').disabled=onCnt===0;
  document.getElementById('tally').textContent='Showing '+vis.length+' of '+tracks.length;

  const MAX=400;
  const rows=vis.slice(0,MAX).map(t=>{
    const on=isOn(t);
    const art=t.image?`<img class="art" src="${t.image}" alt="" loading="lazy">`
                     :`<div class="art-ph">♪</div>`;
    return `<div class="row${on?'':' off'}" onclick="toggle('${t.id}')">
      ${art}
      <div class="info">
        <div class="tn">${x(t.name)}</div>
        <div class="an">${x(t.artist)}</div>
      </div>
      <div class="bars">
        <div class="br"><span class="bl">⚡</span>
          <div class="bg"><div class="bf" style="width:${Math.round(t.energy*100)}%"></div></div>
        </div>
        <div class="br"><span class="bl">😊</span>
          <div class="bg"><div class="bf" style="width:${Math.round(t.mood*100)}%"></div></div>
        </div>
      </div>
    </div>`;
  }).join('');

  const more=vis.length>MAX?`<div style="text-align:center;padding:18px;color:var(--dim);font-size:12px">${vis.length-MAX} more — use search or adjust sliders</div>`:'';
  document.getElementById('box').innerHTML=`<div class="list">${rows}${more}</div>`;
}

function x(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

async function doSave(){
  const ids=tracks.filter(t=>isOn(t)).map(t=>t.id);
  const btn=document.getElementById('savebtn');
  btn.disabled=true;btn.textContent='Saving…';
  try{
    const r=await fetch('/api/save',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({track_ids:ids})});
    const d=await r.json();
    toast(d.success?'✓ Saved '+d.count+' songs to your Graduation playlist!':'Error — try again');
  }catch(e){toast('Error — try again');}
  btn.disabled=false;btn.textContent='Save to Graduation Playlist';
}

function toast(msg){
  const el=document.getElementById('toast');
  el.textContent=msg;el.classList.add('up');
  setTimeout(()=>el.classList.remove('up'),3500);
}

init();
</script>
</body>
</html>"""

if __name__ == "__main__":
    print("Starting at http://localhost:5001")
    webbrowser.open("http://localhost:5001")
    app.run(port=5001, debug=False, use_reloader=False)
