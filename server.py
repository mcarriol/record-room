#!/usr/bin/env python3
"""Record Room server: serves the room and a tiny JSON API for the visitor counter, the doodleboard and gifted records.

  python3 server.py [port]            (default 5178)

Data lives in ./data (visitors.json, doodles.json + doodles/*.png, gifts.json). Standard library only.
Moderation: set ADMIN_KEY in the environment, then
  curl -X DELETE "http://localhost:5178/api/doodles/<id>?key=$ADMIN_KEY"
  curl -X DELETE "http://localhost:5178/api/gifts/<id>?key=$ADMIN_KEY"
"""
import base64, hashlib, html, json, os, re, sys, threading, time, urllib.parse, urllib.request, uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
DOODLES = os.path.join(DATA, "doodles")
os.makedirs(DOODLES, exist_ok=True)
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")
LOCK = threading.Lock()
RATE = {}                               # (ip, kind) -> last timestamp

MAX_DOODLE_BYTES = 350_000
MAX_DOODLES, MAX_GIFTS = 500, 200


def load(name, default):
    try:
        with open(os.path.join(DATA, name)) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(name, obj):
    tmp = os.path.join(DATA, name + ".tmp")
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, os.path.join(DATA, name))


def clean(text, n):
    text = re.sub(r"[\x00-\x1f\x7f]", "", str(text or "")).strip()
    return text[:n]


def limited(ip, kind, seconds):
    now = time.time()
    last = RATE.get((ip, kind), 0)
    if now - last < seconds:
        return int(seconds - (now - last)) + 1
    RATE[(ip, kind)] = now
    return 0


def soundcloud_track(url):
    """Look a public SoundCloud track up via oEmbed. Returns metadata or raises ValueError with a friendly message."""
    host = urllib.parse.urlparse(url).netloc.lower()
    if host not in ("soundcloud.com", "www.soundcloud.com", "m.soundcloud.com", "on.soundcloud.com"):
        raise ValueError("That isn't a SoundCloud link.")
    q = "https://soundcloud.com/oembed?format=json&url=" + urllib.parse.quote(url, safe="")
    try:
        with urllib.request.urlopen(urllib.request.Request(q, headers={"User-Agent": "RecordRoom/1.0"}), timeout=10) as r:
            o = json.load(r)
    except Exception:
        raise ValueError("SoundCloud couldn't find that track. Check the link is public.")
    src = re.search(r'src="([^"]+)"', o.get("html", ""))
    inner = urllib.parse.parse_qs(urllib.parse.urlparse(src.group(1).replace("&amp;", "&")).query).get("url", [""])[0] if src else ""
    if "/playlists/" in inner:
        raise ValueError("The cart takes single tracks. Paste a link to one song, not a playlist.")
    if "/tracks/" not in inner:
        raise ValueError("SoundCloud won't embed that track.")
    title = o.get("title", "")
    m = re.match(r"^(.*) by (.*)$", title)
    return {"api": inner, "title": (m.group(1) if m else title)[:120], "artist": (o.get("author_name") or (m.group(2) if m else ""))[:80],
            "artwork": o.get("thumbnail_url", "")}


OG_CACHE = {}                           # playlist url -> (expires, title, by)
ROOMS = ("pink", "white", "red")


def playlist_meta(url):
    """Title and curator of a public SoundCloud playlist, for link previews. Cached; never raises."""
    hit = OG_CACHE.get(url)
    if hit and hit[0] > time.time():
        return hit[1], hit[2]
    title = by = ""
    try:
        q = "https://soundcloud.com/oembed?format=json&url=" + urllib.parse.quote(url, safe="")
        with urllib.request.urlopen(urllib.request.Request(q, headers={"User-Agent": "RecordRoom/1.0"}), timeout=4) as r:
            o = json.load(r)
        m = re.match(r"^(.*) by (.*)$", o.get("title", ""))
        title, by = (m.group(1) if m else o.get("title", "")), (o.get("author_name") or (m.group(2) if m else ""))
    except Exception:
        pass
    OG_CACHE[url] = (time.time() + 3600, title[:120], by[:80])
    return OG_CACHE[url][1], OG_CACHE[url][2]


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):
        line = fmt % args
        if "/api/" in line or "code 4" in line or "code 5" in line:
            sys.stderr.write("%s %s\n" % (self.address_string(), line))

    # ---- helpers
    def ip(self):
        return self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()

    def body(self, limit=600_000):
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            raise ValueError("That's too big.")
        return json.loads(self.rfile.read(n) or b"{}")

    def reply(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def end_headers(self):
        # never let the browser cache stale room code while we iterate
        if self.path.endswith((".html", "/")) or self.path.startswith("/?"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def serve_index(self, query):
        """index.html with a link preview that names the shared playlist and shows the chosen room."""
        q = urllib.parse.parse_qs(query)
        room = (q.get("room") or ["pink"])[0]
        room = room if room in ROOMS else "pink"
        lst = (q.get("list") or [""])[0]
        url = "https://soundcloud.com/" + lst if re.fullmatch(r"[\w\-./]{1,200}", lst or "-") and lst else (q.get("url") or [""])[0]
        title, by = playlist_meta(url) if re.match(r"^https://(www\.|m\.|on\.)?soundcloud\.com/", url or "") else ("", "")
        head = f"{title} · Record Room" if title else "Record Room"
        desc = (f"{title}, selected by {by}. " if title and by else f"{title}. " if title else "") + \
            "Pull a record off the shelf, drop it on the turntable, sign the guestbook and leave a record for the next visitor."
        host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or "localhost"
        scheme = self.headers.get("X-Forwarded-Proto") or "http"
        base = f"{scheme}://{host}"
        e = lambda v: html.escape(v, quote=True)
        tags = "\n".join([
            f'<meta name="description" content="{e(desc)}">',
            f'<meta property="og:type" content="website">', f'<meta property="og:site_name" content="Record Room">',
            f'<meta property="og:title" content="{e(head)}">', f'<meta property="og:description" content="{e(desc)}">',
            f'<meta property="og:image" content="{e(base)}/assets/og-{room}.jpg">', '<meta property="og:image:width" content="1200">', '<meta property="og:image:height" content="630">',
            f'<meta property="og:url" content="{e(base + self.path)}">',
            '<meta name="twitter:card" content="summary_large_image">', f'<meta name="twitter:title" content="{e(head)}">',
            f'<meta name="twitter:description" content="{e(desc)}">', f'<meta name="twitter:image" content="{e(base)}/assets/og-{room}.jpg">',
        ])
        with open(os.path.join(ROOT, "index.html"), encoding="utf-8") as f:
            page = f.read().replace("<title>Record Room</title>", f"<title>{e(head)}</title>", 1).replace("<!--OG-->", tags, 1)
        data = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---- routes
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        path = u.path
        if path in ("/", "/index.html"):
            return self.serve_index(u.query)
        if path == "/api/stats":
            return self.reply({"visitors": load("visitors.json", {"count": 0})["count"]})
        if path == "/api/doodles":
            return self.reply({"doodles": load("doodles.json", [])[:120]})
        if path == "/api/gifts":
            return self.reply({"gifts": load("gifts.json", [])})
        if path.startswith("/data/") and not path.startswith("/data/doodles/"):
            return self.send_error(404)                      # only doodle images are public
        return super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == "/api/visit":
                b = self.body(2_000)
                vid = hashlib.sha256(clean(b.get("id"), 64).encode()).hexdigest()[:24]
                with LOCK:
                    v = load("visitors.json", {"count": 0, "ids": []})
                    ids = set(v["ids"])
                    if vid and vid not in ids:
                        ids.add(vid)
                        v = {"count": v["count"] + 1, "ids": sorted(ids)}
                        save("visitors.json", v)
                return self.reply({"visitors": v["count"]})

            if path == "/api/doodles":
                wait = limited(self.ip(), "doodle", 20)
                if wait:
                    return self.reply({"error": f"Give it {wait}s before signing again."}, 429)
                b = self.body(MAX_DOODLE_BYTES * 2)
                name, note = clean(b.get("name"), 24), clean(b.get("note"), 90)
                img = str(b.get("image", ""))
                if not img.startswith("data:image/png;base64,"):
                    return self.reply({"error": "The drawing didn't come through. Try again."}, 400)
                raw = base64.b64decode(img.split(",", 1)[1], validate=True)
                if len(raw) > MAX_DOODLE_BYTES or not raw.startswith(b"\x89PNG"):
                    return self.reply({"error": "That drawing is too large."}, 400)
                did = uuid.uuid4().hex[:12]
                with open(os.path.join(DOODLES, did + ".png"), "wb") as f:
                    f.write(raw)
                item = {"id": did, "name": name or "Anonymous", "note": note, "img": f"/data/doodles/{did}.png", "at": int(time.time())}
                with LOCK:
                    items = [item] + load("doodles.json", [])
                    for old in items[MAX_DOODLES:]:
                        try: os.remove(os.path.join(DOODLES, old["id"] + ".png"))
                        except OSError: pass
                    save("doodles.json", items[:MAX_DOODLES])
                return self.reply({"doodle": item}, 201)

            if path == "/api/gifts":
                wait = limited(self.ip(), "gift", 30)
                if wait:
                    return self.reply({"error": f"Give it {wait}s before leaving another record."}, 429)
                b = self.body(4_000)
                url = clean(b.get("url"), 400)
                sender = clean(b.get("from"), 24) or "A visitor"
                meta = soundcloud_track(url)
                item = {"id": uuid.uuid4().hex[:12], "url": url, "from": sender, "at": int(time.time()), **meta}
                with LOCK:
                    items = load("gifts.json", [])
                    if any(g["api"] == meta["api"] for g in items):
                        return self.reply({"error": "That record is already on the shelf."}, 409)
                    save("gifts.json", ([item] + items)[:MAX_GIFTS])
                return self.reply({"gift": item}, 201)
        except ValueError as e:
            return self.reply({"error": str(e)}, 400)
        except Exception:
            return self.reply({"error": "Something went wrong. Try again."}, 500)
        self.send_error(404)

    def do_DELETE(self):
        u = urllib.parse.urlparse(self.path)
        key = urllib.parse.parse_qs(u.query).get("key", [""])[0]
        if not ADMIN_KEY or key != ADMIN_KEY:
            return self.reply({"error": "Not allowed."}, 403)
        m = re.match(r"^/api/(doodles|gifts)/([0-9a-f]{12})$", u.path)
        if not m:
            return self.send_error(404)
        kind, iid = m.groups()
        with LOCK:
            items = load(f"{kind}.json", [])
            save(f"{kind}.json", [x for x in items if x["id"] != iid])
        if kind == "doodles":
            try: os.remove(os.path.join(DOODLES, iid + ".png"))
            except OSError: pass
        return self.reply({"deleted": iid})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5178
    print(f"Record Room on http://localhost:{port}")
    ThreadingHTTPServer(("", port), Handler).serve_forever()
