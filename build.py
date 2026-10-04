#!/usr/bin/env python3
"""Builds a static Stremio/Nuvio catalog addon: anime with an official Hindi dub, newest Hindi release first.

Source: Anime Mirchi's Crunchyroll Hindi-dub lineup table (one row per season/cour, with the Hindi release date).
Each row is reduced to its show, matched on TMDB (TMDB_API_KEY env), and emitted with its IMDb id (tmdb: id as
fallback), so Nuvio pulls the real metadata and streams from the user's other addons.

Usage: TMDB_API_KEY=... build.py OUT_DIR
"""
import concurrent.futures as cf
import datetime
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

SOURCE = "https://animemirchi.com/complete-crunchyroll-hindi-dubbed-anime-list/"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}
PAGE = 100
KEY = os.environ["TMDB_API_KEY"]


def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode("utf-8", "ignore")


def tmdb(path, **q):
    return json.loads(fetch(f"https://api.themoviedb.org/3{path}?{urllib.parse.urlencode({**q, 'api_key': KEY})}"))


def rows():
    """(title, hindi release date) for every lineup table row."""
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", fetch(SOURCE), flags=re.S)
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        cells = [html.unescape(re.sub("<[^>]+>", "", c)).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        if len(cells) == 4 and cells[0].isdigit():
            try:
                yield cells[1], datetime.datetime.strptime(cells[2].replace("Sept ", "Sep "), "%b %d, %Y").date()
            except ValueError:
                continue


def base_title(t):
    """'Demon Slayer: Kimetsu no Yaiba – Mugen Train Arc (Season 2 – Cour 1)' -> 'Demon Slayer: Kimetsu no Yaiba'."""
    t = re.split(r"\s+[–—]\s+|\s+\(", t)[0]
    t = re.sub(r"\s+(Season|Part|Cour)\s*\d+.*$|\s+\d+(st|nd|rd|th)\s+Season.*$", "", t, flags=re.I)
    return t.strip(" -:")


def match(title):
    """Best TMDB anime match: Japanese animation TV first, then movie."""
    for kind in ("tv", "movie"):
        res = tmdb(f"/search/{kind}", query=title).get("results", [])
        res = [r for r in res if 16 in r.get("genre_ids", []) and r.get("original_language") in ("ja", "zh", "ko")] or []
        if res:
            r = res[0]
            ext = tmdb(f"/{kind}/{r['id']}/external_ids")
            return {
                "id": ext.get("imdb_id") or f"tmdb:{r['id']}",
                "type": "series" if kind == "tv" else "movie",
                "name": r.get("name") or r.get("title"),
                "poster": f"https://image.tmdb.org/t/p/w342{r['poster_path']}" if r.get("poster_path") else None,
                "background": f"https://image.tmdb.org/t/p/w1280{r['backdrop_path']}" if r.get("backdrop_path") else None,
                "description": r.get("overview", ""),
            }
    return None


def main(out):
    latest = {}
    for title, day in rows():
        b = base_title(title)
        if b and (b not in latest or day > latest[b]):
            latest[b] = day
    with cf.ThreadPoolExecutor(8) as ex:
        found = dict(zip(latest, ex.map(match, latest)))
    shows = {}
    for b, m in found.items():
        if m and (m["id"] not in shows or latest[b] > shows[m["id"]]["_day"]):
            shows[m["id"]] = {**m, "_day": latest[b]}
    out = Path(out)
    catalogs = [("series", "hindi-dub-anime", "Hindi Dubbed Anime"), ("movie", "hindi-dub-anime-movies", "Hindi Dubbed Anime Movies")]
    for kind, cid, _ in catalogs:
        items = sorted((s for s in shows.values() if s["type"] == kind), key=lambda s: s["_day"], reverse=True)
        metas = [{k: v for k, v in s.items() if k != "_day" and v} | {"releaseInfo": f"Hindi {s['_day']:%b %Y}", "genres": ["Anime", "Hindi Dub"]} for s in items]
        d = out / "catalog" / kind / cid
        d.mkdir(parents=True, exist_ok=True)
        for start in range(0, max(len(metas), 1), PAGE):
            name = f"{cid}.json" if start == 0 else f"{cid}/skip={start}.json"
            (out / "catalog" / kind / name).write_text(json.dumps({"metas": metas[start:start + PAGE]}, ensure_ascii=False))
        print(f"{cid}: {len(metas)} titles")
    unmatched = sorted(b for b, m in found.items() if not m)
    print(f"unmatched {len(unmatched)}: {unmatched[:20]}")
    manifest = {
        "id": "community.hindidub.anime", "version": f"1.0.{datetime.date.today():%Y%m%d}",
        "name": "Hindi Dubbed Anime", "description": "Anime with an official Crunchyroll Hindi dub, newest first.",
        "resources": ["catalog"], "types": ["series", "movie"], "idPrefixes": ["tt", "tmdb:"],
        "catalogs": [{"type": t, "id": c, "name": n, "extra": [{"name": "skip"}]} for t, c, n in catalogs],
        "behaviorHints": {"configurable": False},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
