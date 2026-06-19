import os, re, time, asyncio, json, subprocess, shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

app = FastAPI()
INDEX = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
COOKIES = str(Path(__file__).parent / "cookies.txt")
YTDLP = shutil.which("yt-dlp") or "yt-dlp"
executor = ThreadPoolExecutor(max_workers=8)
_cache: dict = {}
CACHE_TTL = 300

def extract_vid(url: str):
    m = re.search(r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([a-zA-Z0-9_-]{11})", url)
    return m.group(1) if m else None

def human_size(b):
    if not b: return "?"
    for unit in ["B","KB","MB","GB"]:
        if b < 1024: return f"~{b:.0f} {unit}"
        b /= 1024
    return f"~{b:.1f} GB"

def _fetch(url: str) -> dict:
    vid = extract_vid(url)
    if not vid: return {"error": "invalid_url"}

    if vid in _cache:
        ts, data = _cache[vid]
        if time.time() - ts < CACHE_TTL:
            return data

    # Dùng yt-dlp CLI với --dump-json
    node_bin = shutil.which("node") or "/usr/bin/node"
    cmd = [
        YTDLP,
        "--cookies", COOKIES,
        "--js-runtimes", f"node:{node_bin}",
        "--extractor-args", "youtube:player_client=web",
        "--dump-json",
        "--no-playlist",
        "--quiet",
        url,
    ]
    env = os.environ.copy()
    env["PATH"] = f"/usr/bin:/usr/local/bin:{env.get('PATH','')}"
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=40, env=env)
        if result.returncode != 0:
            err = result.stderr.lower()
            if "private" in err or "unavailable" in err: return {"error": "private"}
            if "playlist" in err: return {"error": "playlist"}
            return {"error": "network", "detail": result.stderr[:300]}
        info = json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return {"error": "network", "detail": "timeout"}
    except Exception as e:
        return {"error": "network", "detail": str(e)[:200]}

    seen, formats = set(), []
    for f in reversed(info.get("formats", [])):
        vc, ac, h = f.get("vcodec","none"), f.get("acodec","none"), f.get("height")
        if vc=="none" or ac=="none" or not h: continue
        if not f.get("url"): continue
        key = (h, f.get("ext",""))
        if key in seen: continue
        seen.add(key)
        fps = f.get("fps")
        formats.append({
            "type":"video+audio", "quality":f"{h}p",
            "ext":f.get("ext","").upper(),
            "size":human_size(f.get("filesize") or f.get("filesize_approx")),
            "fps":f"{int(fps)}fps" if fps else "—",
            "url":f.get("url",""),
        })
    for f in reversed(info.get("formats",[])):
        if f.get("vcodec","none") != "none": continue
        if f.get("acodec","none") == "none": continue
        if not f.get("url"): continue
        if f.get("ext","") not in ("m4a","webm","mp3","opus"): continue
        abr = f.get("abr")
        formats.append({
            "type":"audio",
            "quality":f"{int(abr)}kbps" if abr else "audio",
            "ext":f.get("ext","").upper(),
            "size":human_size(f.get("filesize") or f.get("filesize_approx")),
            "fps":"—", "url":f.get("url",""),
        })
        break

    dur = info.get("duration", 0) or 0
    data = {
        "title":     info.get("title","Unknown"),
        "channel":   info.get("uploader","Unknown"),
        "duration":  f"{int(dur)//60}:{int(dur)%60:02d}",
        "views":     f"{info.get('view_count',0):,}",
        "thumbnail": info.get("thumbnail",""),
        "formats":   formats[:15],
    }
    _cache[vid] = (time.time(), data)
    if len(_cache) > 500:
        for k in sorted(_cache, key=lambda k: _cache[k][0])[:100]:
            del _cache[k]
    return data

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(INDEX)

@app.get("/api/info")
async def api_info(url: str = ""):
    url = url.strip()
    if not url: return JSONResponse({"error":"empty"})
    if not extract_vid(url): return JSONResponse({"error":"invalid_url"})
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, _fetch, url)
    return JSONResponse(result)

@app.get("/api/test")
async def api_test():
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _fetch, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")

@app.get("/api/debug")
async def api_debug():
    node = shutil.which("node") or "NOT FOUND"
    try: nv = subprocess.check_output(["node","--version"], text=True).strip()
    except: nv = "error"
    try:
        import yt_dlp_ejs; ejs = "installed"
    except: ejs = "NOT INSTALLED"
    import yt_dlp
    return {"node": node, "node_v": nv, "ytdlp": yt_dlp.version.__version__, "ejs": ejs, "ytdlp_bin": YTDLP}

@app.get("/health")
async def health():
    return {"status":"ok","cache":len(_cache)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, log_level="info")
