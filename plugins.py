#!/usr/bin/env python3
"""Writes two tiny Nuvio plugin repositories that re-use D3adlyRocket's All-in-One-Nuvio scrapers by absolute URL:
  plugins/hindi-fast/manifest.json       castle (Hindi streams, ~1 s)
  plugins/hindi-anime-ott/manifest.json  animedekho (Hindi-dubbed anime), netmirror (Netflix/Prime/Hotstar, Hindi track)
Split in two so the fast one lands on its own even when "Group plugin providers by repository" is on.
Usage: plugins.py OUT_DIR"""
import json, sys, urllib.request
from pathlib import Path
UP = "https://raw.githubusercontent.com/D3adlyRocket/All-in-One-Nuvio/refs/heads/main/"
REPOS = {"hindi-fast": ("Hindi Fast (Castle)", ["castle"]), "hindi-anime-ott": ("Hindi Anime + OTT", ["animedekho", "netmirror"])}
up = json.load(urllib.request.urlopen(urllib.request.Request(UP + "manifest.json", headers={"User-Agent": "Mozilla/5.0"}), timeout=60))
by_id = {s["id"]: s for s in up["scrapers"]}
for slug, (name, ids) in REPOS.items():
    scrapers = [{**by_id[i], "filename": UP + by_id[i]["filename"].lstrip("/"), "enabled": True} for i in ids if i in by_id]
    d = Path(sys.argv[1]) / "plugins" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps({"name": name, "version": up.get("version", "1.0.0"), "scrapers": scrapers}, ensure_ascii=False, indent=1))
    print(slug, [s["id"] + "@" + s["version"] for s in scrapers])
