#!/usr/bin/env python3
"""
extract_from_html_map.py — derive structured data for the Repo Workbench Architecture Map
from the canonical concept doc (docs/ATLAS ARCHITECTURE MAP.html) + the checklist corpus.

Pipeline:  HTML map  ->  this script  ->  data/{audit_findings,sdlc_phases,map_tables}.yaml
           items.jsonl -> this script -> public/atlas-ui/architecture-map.checklist.json
Then generate_map_data.py assembles architecture-map.data.json (repo-keyed) from these.
Re-run after editing the HTML map; the Workbench views are NOT hand-maintained.
"""
import re, json, yaml
from pathlib import Path
from html.parser import HTMLParser
from collections import Counter

ROOT = Path(__file__).resolve().parents[3]
HTML = ROOT / "docs/ATLAS ARCHITECTURE MAP.html"
DATA = ROOT / "infrastructure/scripts/architecture_map/data"
ITEMS = ROOT / "platform/systems/18_registry/dev_checklist.items.jsonl"
CHK = ROOT / "apps/frontend/shell/public/atlas-ui/architecture-map.checklist.json"

class Grab(HTMLParser):
    def __init__(s):
        super().__init__(); s.tables=[]; s.cur=None; s.row=None; s.cell=None; s.cellTag=None
    def handle_starttag(s,t,a):
        if t=="table": s.cur={"head":[],"rows":[]}
        elif t=="tr" and s.cur is not None: s.row=[]
        elif t in("td","th") and s.row is not None: s.cell=[]; s.cellTag=t
    def handle_data(s,d):
        if s.cell is not None: s.cell.append(d)
    def handle_endtag(s,t):
        if t in("td","th") and s.cell is not None:
            txt=re.sub(r"\s+"," ","".join(s.cell)).strip()
            (s.cur["head"] if s.cellTag=="th" else s.row).append(txt); s.cell=None
        elif t=="tr" and s.row is not None:
            if s.row: s.cur["rows"].append(s.row)
            s.row=None
        elif t=="table" and s.cur is not None: s.tables.append(s.cur); s.cur=None

def md_table(md_path, *sig):
    """Extract the first markdown table whose header matches all sig terms."""
    rows = []
    lines = Path(md_path).read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|") and i+1 < len(lines) and re.match(r"^\s*\|?[\s:|-]+\|", lines[i+1]):
            head = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            hl = [h.lower() for h in head]
            if all(any(s in h for h in hl) for s in sig):
                j = i+2
                while j < len(lines) and lines[j].lstrip().startswith("|"):
                    rows.append([c.strip().replace("\\|", "|") for c in lines[j].strip().strip("|").split("|")])
                    j += 1
                return rows
        i += 1
    return rows

def main():
    g=Grab(); g.feed(HTML.read_text(encoding="utf-8"))
    def tbl(*sig):
        for t in g.tables:
            h=[x.lower() for x in t["head"]]
            if all(any(x in c for c in h) for x in sig): return t["rows"]
        return []
    SPEC_MD = ROOT / "docs/Atlas Spec vs Build.md"
    spec_vs_build = [{"category":r[0],"spec":r[1],"build":r[2],"verdict":r[3]}
                     for r in md_table(SPEC_MD, "category","spec","build","verdict") if len(r)>=4]
    findings=[{"id":r[0],"severity":r[1],"category":r[2],"finding":r[3],"status":r[4],"evidence":r[5]}
              for r in tbl("id","severity","finding","status","evidence") if len(r)>=6]
    sdlc=[{"phase":r[0],"spec_state":r[1],"build_state":r[2],"verdict":r[3],"key_gap":r[4]}
          for r in tbl("phase","spec","build","verdict") if len(r)>=5]
    content={
     "api_routes":[{"method":r[0],"route":r[1],"auth":r[2],"desc":r[3]} for r in tbl("method","route","auth") if len(r)>=4],
     "mcp_tools":[{"tool":r[0],"type":r[1],"impl":r[2],"desc":r[3]} for r in tbl("tool","type","implementation") if len(r)>=4],
     "capability_registry":[{"cap":r[0],"status":r[1],"category":r[2],"via":r[3]} for r in tbl("cap_* executor","status") if len(r)>=4],
     "integration_components":[{"component":r[0],"status":r[1],"evidence":r[2]} for r in tbl("component","status","evidence") if len(r)>=3],
     "doc_capture":[{"component":r[0],"status":r[1],"evidence":r[2]} for r in tbl("capture component","status") if len(r)>=3],
     "drift_classes":[{"cls":r[0],"findings":r[1],"example":r[2]} for r in tbl("drift class","findings") if len(r)>=3],
     "roadmap_top5":[{"n":r[0],"category":r[1],"capability":r[2],"why":r[3]} for r in tbl("category (core","proposed capability") if len(r)>=4],
     "roadmap_clusters":[{"cluster":r[0],"capability":r[1],"closes":r[2],"target":r[3]} for r in tbl("domain cluster","proposed capability") if len(r)>=4],
     "spec_vs_build":spec_vs_build,
    }
    DATA.mkdir(parents=True, exist_ok=True)
    yaml.safe_dump({"schema_version":"1.0","source":"docs/ATLAS ARCHITECTURE MAP.html (audit findings table)","count":len(findings),"findings":findings}, open(DATA/"audit_findings.yaml","w"), sort_keys=False, allow_unicode=True)
    yaml.safe_dump({"schema_version":"1.0","source":"docs/ATLAS ARCHITECTURE MAP.html (17-phase SDLC comparison)","count":len(sdlc),"phases":sdlc}, open(DATA/"sdlc_phases.yaml","w"), sort_keys=False, allow_unicode=True)
    yaml.safe_dump({"schema_version":"1.0","source":"docs/ATLAS ARCHITECTURE MAP.html","content":content}, open(DATA/"map_tables.yaml","w"), sort_keys=False, allow_unicode=True)

    tree={}
    for line in ITEMS.read_text().splitlines():
        it=json.loads(line); tree.setdefault(it["category"],{}).setdefault(it["section"],[]).append(it["item"])
    cats=[{"name":c,"sections":[{"name":s,"items":items} for s,items in secs.items()]} for c,secs in tree.items()]
    n=sum(len(s["items"]) for c in cats for s in c["sections"])
    json.dump({"_meta":{"categories":len(cats),"items":n},"categories":cats}, open(CHK,"w"))
    print(f"findings={len(findings)} sdlc={len(sdlc)} tables={ {k:len(v) for k,v in content.items()} }")
    print(f"checklist.json: {len(cats)} categories / {n} items")

if __name__ == "__main__":
    main()
