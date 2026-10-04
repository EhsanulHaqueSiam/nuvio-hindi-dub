#!/usr/bin/env python3
"""Builds Nuvio plugin repositories from the community library (nuvio-plugin-library.vercel.app) + a few extra
Indian repos: one copy of every site, nothing foreign-language-only, code loaded from the original repos by absolute URL.

  plugins/hindi-fast        castle                      (Hindi streams, ~1 s; own repo so it never waits)
  plugins/hindi-anime-ott   animedekho, netmirror       (Hindi-dubbed anime; Netflix/Prime/Hotstar with Hindi track)
  plugins/indian            Hindi / Bangla / South Indian sites
  plugins/anime-asian       anime + Asian drama sites
  plugins/english           English / multi-language sites
Scrapers whose code file no longer loads are dropped at build time.

Duplicates (same site in several repos) keep the copy from the most actively maintained repo (PRIORITY).
Usage: plugins.py OUT_DIR"""
import concurrent.futures as cf, json, re, sys, urllib.request
from pathlib import Path

LIBRARY_API = "https://nuvio-plugin-library.vercel.app/api/notion/326981dcb87e80f6b9f6f23469a00fd3"
AIO = "https://raw.githubusercontent.com/D3adlyRocket/All-in-One-Nuvio/refs/heads/main/manifest.json"
EXTRA = {  # repo manifest -> scraper ids to take (Indian sites the library lacks)
    "https://raw.githubusercontent.com/Niloy-Sarker/nuvio-plugins/master/manifest.json": None,   # DhakaFlix (BDIX)
    "https://raw.githubusercontent.com/hihihihihiiray/nuvio-plugins/main/manifest.json": {"nuvio-bollyflix"},
    "https://raw.githubusercontent.com/D3adlyRocket/Hindi-Nuvio/main/manifest.json": {"cinestream", "flixindia", "hdmovie2"},
}
PRIORITY = ["D3adlyRocket/All-in-One-Nuvio", "phisher98", "eclipsia", "PirateZoro9", "yoruix", "Niloy-Sarker",
            "hihihihihiiray", "D3adlyRocket/Hindi-Nuvio", "CENSORED", "Abinanthankv"]
FOREIGN_REPOS = {"Turkish Nuvio", "MoOnCrOwN-NUVİO", "Wekmed Turkish Repo", "Latino Providers", "Nuvio Latino",
                 "saimuel-nuvio-repo", "Gowaru's Repo"}
# known broken copies: placeholder clip, dead domains, download-page links
BROKEN = {("CENSORED", "moviebox"), ("phisher98", "toonstream"), ("phisher98", "toonhub"),
          ("D3adlyRocket/All-in-One-Nuvio", "animeworld"), ("Abinanthankv", "toonhub")}
SKIP_SITES = {"torrentio"}   # AIOStreams already runs Torrentio (with TorBox); a plugin copy would only duplicate it
HINDI = {"hindi-fast": ("Hindi Fast (Castle)", ["castle"]), "hindi-anime-ott": ("Hindi Anime + OTT", ["animedekho", "netmirror"])}
INDIAN, ASIAN, OK = {"hi", "bn", "ta", "te", "ml", "kn", "mr", "pa", "gu"}, {"ja", "ko", "zh", "th"}, {"en", "multi"} | {"hi", "bn", "ta", "te", "ml"} | {"ja", "ko", "zh"}

def get(u):
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60))

def norm(s):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\s*\(.*?\)", "", s.lower()))

def rank(url):
    return next((i for i, p in enumerate(PRIORITY) if p.lower() in url.lower()), len(PRIORITY))

def library_urls():
    out = []
    def walk(o):
        if isinstance(o, dict): [walk(v) for v in o.values()]
        elif isinstance(o, list): [walk(v) for v in o]
        elif isinstance(o, str) and re.match(r"https?://\S+manifest\.json$", o) and o not in out: out.append(o)
    walk(get(LIBRARY_API))
    return out

def absolute(manifest_url, filename):
    return filename if filename.startswith(("http://", "https://")) else manifest_url.rsplit("/", 1)[0] + "/" + filename.lstrip("/")

def main(out):
    out = Path(out)
    candidates = {}                     # site -> (rank, scraper, repo name, langs)
    site_langs = {}                     # site -> languages seen on any copy
    for url in library_urls() + list(EXTRA):
        try: m = get(url)
        except Exception as e:
            print("skip dead repo", url, e); continue
        repo = m.get("name", url)
        for s in m.get("scrapers", []):
            if not s.get("enabled", True): continue
            if EXTRA.get(url) and s["id"] not in EXTRA[url]: continue
            if any(p.lower() in url.lower() and s["id"].lower() == sid for p, sid in BROKEN): continue
            site = norm(s.get("name") or s["id"])
            if site in SKIP_SITES: continue
            langs = set(s.get("contentLanguage") or [])
            if repo in FOREIGN_REPOS and not (langs & OK - {"en"}): continue        # French/Turkish/Spanish/Portuguese-only
            site_langs.setdefault(site, set()).update(langs)
            entry = (rank(url), {**s, "filename": absolute(url, s["filename"]), "enabled": True}, repo, langs)
            if site not in candidates or entry[0] < candidates[site][0]: candidates[site] = entry
    hindi_ids = {i for _, ids in HINDI.values() for i in ids}
    groups = {"indian": [], "anime-asian": [], "english": []}
    for site, (_, s, repo, _l) in sorted(candidates.items()):
        langs = site_langs[site]
        if site in hindi_ids or norm(s["id"]) in hindi_ids: continue                 # already in the Hindi repos
        g = "indian" if langs & INDIAN else "anime-asian" if langs & ASIAN else "english"
        groups[g].append(s)
    aio = {s["id"]: s for s in get(AIO)["scrapers"]}
    repos = {slug: (name, [{**aio[i], "filename": absolute(AIO, aio[i]["filename"]), "enabled": True} for i in ids if i in aio])
             for slug, (name, ids) in HINDI.items()}
    repos.update({"indian": ("Nuvio Indian", groups["indian"]), "anime-asian": ("Nuvio Anime & Asian", groups["anime-asian"]),
                  "english": ("Nuvio English", groups["english"])})
    def loads(s):                                           # drop scrapers whose code file is gone upstream
        try: return urllib.request.urlopen(urllib.request.Request(s["filename"], headers={"User-Agent": "Mozilla/5.0"}), timeout=30).status == 200
        except Exception: return False
    with cf.ThreadPoolExecutor(16) as ex:
        alive = dict(zip([s["filename"] for _, sc in repos.values() for s in sc], ex.map(loads, [s for _, sc in repos.values() for s in sc])))
    for slug, (name, scrapers) in repos.items():
        dead = [s["name"] for s in scrapers if not alive[s["filename"]]]
        if dead: print(f"{slug}: dropped (code file missing) {dead}")
        scrapers = [s for s in scrapers if alive[s["filename"]]]
        seen, uniq = set(), []
        for s in scrapers:                                  # scraper ids must be unique inside one repo
            sid = s["id"]
            while sid in seen: sid += "_"
            seen.add(sid); uniq.append({**s, "id": sid})
        d = out / "plugins" / slug; d.mkdir(parents=True, exist_ok=True)
        (d / "manifest.json").write_text(json.dumps({"name": name, "version": "1.0.0", "scrapers": uniq}, ensure_ascii=False, indent=1))
        print(f"{slug:16} {len(uniq):3} scrapers")

if __name__ == "__main__":
    main(sys.argv[1])
