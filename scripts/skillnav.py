#!/usr/bin/env python3
"""skill-navigator: build a Wing>Room>Zone>Station decision-tree navigator
over a subset of SKILL.md-based skills.

Pipeline (subcommands):
  build    embed leaf skills + cluster into a 4-tier tree (top-down k-means, caps by construction)
  emit     write LLM label batches (one node per entry) for an agent to label
  render   write decision-node SKILL.md + _manifest.json per node + a single root
  relates  inject data-driven RELATES_TO cross-links (centroid cosine, cross-branch)
  walk|find|stats   navigate / verify the built tree

A "leaf" = skill dir with SKILL.md and no _manifest.json (not starting with '_').
Navigator nodes are marked `"navigator": true` in their _manifest.json so a
rebuild deletes navigator-owned nodes and leaves source skills untouched.

Requires: sentence-transformers, scikit-learn, numpy (use a venv that has them).
"""
import os, re, json, math, glob, sys, shutil, argparse, fnmatch
from datetime import datetime, timezone

# ---------- shared helpers ----------
def now(): return datetime.now(timezone.utc).isoformat()

def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()

def write_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def write_json(path, data, **kwargs):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, **kwargs)

def desc_of(folder):
    p = f"{folder}/SKILL.md"
    if not os.path.exists(p): return ""
    t = read_text(p)
    m = re.search(r'description:\s*[>|]?\s*\n?(.*?)(?:\nuser-invokable:|\nargs:|\nmetadata:|\ndisable|\n---)', t, re.S)
    if not m:
        m = re.search(r'description:\s*(.+)', t)
        return m.group(1).strip() if m else ""
    return re.sub(r'\s+', ' ', m.group(1)).strip()

def is_leaf(d):
    return os.path.isdir(d) and os.path.exists(f"{d}/SKILL.md") and not os.path.exists(f"{d}/_manifest.json")

def find_leaves(include, exclude):
    out = []
    for d in sorted(os.listdir(".")):
        if not is_leaf(d) or d.startswith("_"):
            continue
        if include and not any(fnmatch.fnmatch(d, g) for g in include):
            continue
        if exclude and any(fnmatch.fnmatch(d, g) for g in exclude):
            continue
        out.append(d)
    return out

def slug(s):
    s = s.lower().replace("&", " und ").replace("§", "par").replace("/", "-")
    s = s.replace("ä","ae").replace("ö","oe").replace("ü","ue").replace("ß","ss")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return re.sub(r"-+", "-", s)[:60] or "node"

# ---------- i18n for node bodies ----------
LANG = {
 "de": {
   "level": {"wing":"Bereich","room":"Teilbereich","zone":"Themenzone","station":"Themenstation"},
   "node_title": "Entscheidungsknoten",
   "frage": "## Frage\n\nWaehle den Unterbereich von «{title}», der zum Anliegen passt. Lade dessen SKILL.md und entscheide dort weiter, bis zu einem Einzelskill (Blatt).\n\n## Zweige",
   "branch": "- **{lb}**: Stichworte: {hint} -> `../{t}/SKILL.md`",
   "leaf_head": "## Einzelskills (Blaetter)\n\nWaehle das passende Einzelskill und lade dessen Anweisungen. Dies ist die unterste Navigationsebene.",
   "leaf_branch": "- **{lb}**: {hint} -> `../{t}/SKILL.md`",
   "unclear": "## Wenn unklar\n- Mehrere Zweige passen -> nenne die Kandidaten und frage den Nutzer.\n- Kein Zweig passt -> liste die Zweige und bitte um Praezisierung.",
   "relates": "## Verwandte Bereiche (RELATES_TO)\n\nSemantisch nahe Bereiche in anderen Zweigen. Bei Grenzfaellen dort weitersuchen:",
   "routes": "Routes requests to one of {n} sub-skills. Read the relevant sub-skill's full instructions before acting.",
 },
 "en": {
   "level": {"wing":"Area","room":"Sub-area","zone":"Topic zone","station":"Topic station"},
   "node_title": "Decision node",
   "frage": "## Question\n\nPick the part of «{title}» that fits the request. Load its SKILL.md and continue until you reach a leaf skill.\n\n## Branches",
   "branch": "- **{lb}**: keywords: {hint} -> `../{t}/SKILL.md`",
   "leaf_head": "## Leaf skills\n\nPick the matching leaf skill and load its instructions.",
   "leaf_branch": "- **{lb}**: {hint} -> `../{t}/SKILL.md`",
   "unclear": "## If unclear\n- Several branches fit -> name the candidates and ask the user.\n- No branch fits -> list the branches and ask to narrow down.",
   "relates": "## Related areas (RELATES_TO)\n\nClose areas in other branches. Follow them for borderline cases:",
   "routes": "Routes requests to one of {n} sub-skills. Read the relevant sub-skill's full instructions before acting.",
 },
}

# ---------- build ----------
def cmd_build(a):
    import numpy as np
    from sentence_transformers import SentenceTransformer
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import normalize
    from sklearn.feature_extraction.text import TfidfVectorizer
    os.chdir(a.skills_dir)
    os.makedirs(a.work, exist_ok=True)
    include = [g for g in (a.include or "").split(",") if g]
    exclude = [g for g in (a.exclude or "").split(",") if g]
    leaves = find_leaves(include, exclude)
    if a.names_file:
        keep = set(l.strip() for l in read_text(a.names_file).splitlines() if l.strip())
        leaves = [l for l in leaves if l in keep]
    print(f"leaves: {len(leaves)}")
    if len(leaves) < 8: sys.exit("need >=8 leaves to build a tree")
    descs = {l: desc_of(l) for l in leaves}
    texts = [f"{l.replace('-',' ')}: {descs[l][:150]}" for l in leaves]
    print(f"embedding with {a.model} ...")
    emb = normalize(SentenceTransformer(a.model).encode(texts, batch_size=64, show_progress_bar=False))

    GENERIC = set(a.stop.split(",")) if a.stop else set()
    name_docs = [" ".join(t for t in l.split('-') if len(t) >= 4 and t not in GENERIC) for l in leaves]
    vec = TfidfVectorizer(token_pattern=r"[a-zA-Z0-9äöüß]{4,}", max_features=4000)
    NM = vec.fit_transform(name_docs); FEAT = np.array(vec.get_feature_names_out())
    def terms_for(idx, n=6):
        if not idx: return []
        c = np.asarray(NM[idx].mean(axis=0)).ravel()
        return [FEAT[i] for i in c.argsort()[::-1][:n] if c[i] > 0]

    SIZE = {i: s for i, s in enumerate(int(x) for x in a.sizes.split(","))}   # depth0..2 child sizes
    BRANCH = {i: b for i, b in enumerate(int(x) for x in a.branch.split(","))}
    LEVELS = ["wing", "room", "zone", "station"]
    nodes = {}; ctr = [0]
    def newid(lv): ctr[0] += 1; return f"{lv[0]}{ctr[0]}"
    def split(idx, depth, parent):
        lv = LEVELS[depth]; nid = newid(lv)
        nodes[nid] = {"id": nid, "level": lv, "parent": parent, "n": len(idx),
                      "terms": terms_for(idx),
                      "samples": [{"name": leaves[i], "desc": descs[leaves[i]][:120]} for i in idx[:5]],
                      "children": [], "leaves": []}
        if depth == len(LEVELS) - 1:
            nodes[nid]["leaves"] = [leaves[i] for i in idx]; return nid
        k = max(2, min(BRANCH[depth], math.ceil(len(idx) / SIZE[depth]))); k = min(k, len(idx))
        if k < 2:
            nodes[nid]["leaves"] = [leaves[i] for i in idx]; return nid
        lab = KMeans(n_clusters=k, n_init=5, random_state=42).fit_predict(emb[idx])
        for c in range(k):
            sub = [idx[i] for i in range(len(idx)) if lab[i] == c]
            if sub: nodes[nid]["children"].append(split(sub, depth + 1, nid))
        return nid
    roots = []
    km0 = KMeans(n_clusters=a.wings, n_init=5, random_state=42).fit_predict(emb)
    for c in range(a.wings):
        sub = [i for i in range(len(leaves)) if km0[i] == c]
        if sub: roots.append(split(sub, 0, "ROOT"))
    write_json(f"{a.work}/tree.json", {"root_children": roots, "nodes": nodes}, ensure_ascii=False)
    np.save(f"{a.work}/emb.npy", emb)
    write_json(f"{a.work}/leaves.json", leaves)
    from collections import Counter
    lvl = Counter(n["level"] for n in nodes.values())
    sizes = [len(n["leaves"]) for n in nodes.values() if n["level"] == "station"]
    print("levels:", dict(lvl), "| stations:", len(sizes),
          "leaf/station min/med/max:", min(sizes), int(np.median(sizes)), max(sizes))
    print(f"wrote {a.work}/tree.json")

# ---------- emit label batches ----------
def cmd_emit(a):
    t = read_json(f"{a.work}/tree.json"); nodes = t["nodes"]
    os.makedirs(f"{a.work}/labels_in", exist_ok=True)
    os.makedirs(f"{a.work}/labels_out", exist_ok=True)
    order = {"wing":0,"room":1,"zone":2,"station":3}
    items = sorted(nodes.values(), key=lambda n: (order[n["level"]], n["id"]))
    recs = [{"id":n["id"],"level":n["level"],"terms":n["terms"][:6],
             "samples":[s["name"] for s in n["samples"]],"n":n["n"]} for n in items]
    B = a.batch_size
    bs = [recs[i:i+B] for i in range(0, len(recs), B)]
    for i, b in enumerate(bs):
        write_json(f"{a.work}/labels_in/batch_{i:02d}.json", b, ensure_ascii=False)
    print(f"nodes: {len(recs)}  batches: {len(bs)}  -> {a.work}/labels_in/")
    print(f"Have an LLM label each batch -> {a.work}/labels_out/batch_NN.json as {{id:\"Label\"}}.")

# ---------- render ----------
def _load_labels(work):
    L = {}
    for f in glob.glob(f"{work}/labels_out/batch_*.json"): L.update(read_json(f))
    return L

def cmd_render(a):
    os.chdir(a.skills_dir)
    t = read_json(f"{a.work}/tree.json"); nodes = t["nodes"]
    L = _load_labels(a.work); T = LANG[a.lang]
    miss = [i for i in nodes if i not in L]
    print(f"nodes={len(nodes)} labeled={len(L)} missing={len(miss)}")
    if miss:
        print("  missing:", miss[:20])
        if not a.apply: return
    PRE = {"wing":"wing","room":"room","zone":"zone","station":"stn"}
    leafset = set(d for d in os.listdir(".") if is_leaf(d) and not d.startswith("_"))
    used = set(leafset); used.add(a.root)
    dirn = {}
    for nid, n in nodes.items():
        base = f"{PRE[n['level']]}-{slug(L.get(nid, nid))}"; nm = base; k = 2
        while nm in used: nm = f"{base}-{k}"; k += 1
        used.add(nm); dirn[nid] = nm
    label = lambda i: L.get(i, i)
    hint = lambda i: ", ".join(nodes[i]["terms"][:5]) or "-"

    def dedup(cids):
        seen = {}; out = {}
        for c in cids:
            lb = label(c); b = lb; k = 2
            while lb in seen: lb = f"{b} ({k})"; k += 1
            seen[lb] = 1; out[c] = lb
        return out

    def write(name, lvl, title, dsc, branches, leafmode, is_root=False):
        skills = [{"name": t_, "folder_name": t_, "description_at_merge": ""} for _, _, t_ in branches]
        man = {"router_name": name, "skills_dir": a.skills_dir, "created": now(),
               "kind": "root" if is_root else lvl, "navigator": True, "root": is_root, "skills": skills}
        if not a.apply: return
        os.makedirs(name, exist_ok=True)
        write_json(f"{name}/_manifest.json", man, ensure_ascii=False, indent=1)
        if leafmode:
            head = T["leaf_head"]; bl = "\n".join(T["leaf_branch"].format(lb=lb, hint=h, t=t_) for lb, h, t_ in branches)
        else:
            head = T["frage"].format(title=title); bl = "\n".join(T["branch"].format(lb=lb, hint=h, t=t_) for lb, h, t_ in branches)
        avail = ", ".join(f'"{t_}"' for _, _, t_ in branches)
        # The root is user-invokable/auto-discoverable. Agents reach sub-nodes by reading
        # ../<name>/SKILL.md during traversal; sub-nodes stay out of the skill list.
        body = (f"---\nname: {name}\ndescription: >\n  {dsc}\n"
                f"user-invokable: {'true' if is_root else 'false'}\n"
                f"args:\n  - name: skill\n    description: >\n      Direct sub-skill to load. Available: {avail}.\n    required: false\n"
                f"metadata:\n  category: \"router\"\n  kind: \"{'root' if is_root else lvl}\"\n  navigator: \"true\"\n---\n\n"
                f"# {T['node_title']}: {title}  ({T['level'][lvl]})\n\n{T['routes'].format(n=len(branches))}\n\n"
                f"{head}\n{bl}\n\n{T['unclear']}\n")
        write_text(f"{name}/SKILL.md", body)

    if a.apply:
        old = [d for d in os.listdir(".") if os.path.isdir(d) and os.path.exists(f"{d}/_manifest.json")
               and read_json(f"{d}/_manifest.json").get("navigator") and not d.startswith("_")]
        for d in old: shutil.rmtree(d)
        print(f"deleted {len(old)} old navigator nodes")

    nw = 0
    for nid, n in nodes.items():
        lvl = n["level"]; nm = dirn[nid]; ttl = label(nid)
        if n["leaves"]:   # leaf-holder (station, or an intermediate node that bottomed out early)
            br = []
            for l in n["leaves"]:
                d = desc_of(l)[:110]
                br.append((l.replace("-", " "), d or "leaf skill", l))
            dsc = (f"{T['node_title']} ({T['level'][lvl]}) {ttl}: {len(n['leaves'])} leaf skills.")[:1020]
            write(nm, lvl, ttl, dsc, br, True)
        else:
            cids = n["children"]; disp = dedup(cids)
            br = [(disp[c], hint(c), dirn[c]) for c in cids]
            dsc = (f"{T['node_title']} ({T['level'][lvl]}) {ttl} -> {', '.join(disp[c] for c in cids)}.")[:1020]
            write(nm, lvl, ttl, dsc, br, False)
        nw += 1
    # root
    rc = t["root_children"]; disp = dedup(rc)
    br = [(disp[c], hint(c), dirn[c]) for c in rc]
    rdesc = (f"{a.root}: decision-tree entry point. Top areas: {', '.join(disp[c] for c in rc)}. "
             "Answer the question, pick an area, load its SKILL.md, navigate down to the matching leaf skill.")[:1020]
    write(a.root, "wing", a.title or a.root, rdesc, br, False, is_root=True)
    namemap = {nid: dirn[nid] for nid in nodes}; namemap["ROOT"] = a.root
    write_json(f"{a.work}/names.json", namemap, ensure_ascii=False)
    print(f"internal nodes: {nw} + root '{a.root}'  (APPLY={a.apply})")

# ---------- relates ----------
def cmd_relates(a):
    import numpy as np
    os.chdir(a.skills_dir)
    t = read_json(f"{a.work}/tree.json"); nodes = t["nodes"]
    emb = np.load(f"{a.work}/emb.npy"); leaves = read_json(f"{a.work}/leaves.json")
    lidx = {l: i for i, l in enumerate(leaves)}; names = read_json(f"{a.work}/names.json")
    L = _load_labels(a.work); T = LANG[a.lang]
    parent = {nid: n["parent"] for nid, n in nodes.items()}
    def members(nid):
        n = nodes[nid]
        if n["level"] == "station": return n["leaves"]
        out = []
        for c in n["children"]: out += members(c)
        return out
    cent = {}
    for nid in nodes:
        ms = [lidx[l] for l in members(nid) if l in lidx]
        v = emb[ms].mean(0); cent[nid] = v / (np.linalg.norm(v) + 1e-9)
    def wing_of(nid):
        while parent[nid] != "ROOT": nid = parent[nid]
        return nid
    n = 0
    for lv in ("wing", "room"):
        ids = [i for i, x in nodes.items() if x["level"] == lv]
        if not ids: continue
        M = np.array([cent[i] for i in ids]); S = M @ M.T
        for r, aid in enumerate(ids):
            wa = wing_of(aid)
            picks = []
            for _, b in sorted(((S[r, c], ids[c]) for c in range(len(ids)) if ids[c] != aid), reverse=True):
                if lv == "room" and wing_of(b) == wa: continue
                picks.append(b)
                if len(picks) == 3: break
            p = f"{names[aid]}/SKILL.md"
            if not picks or not os.path.exists(p): continue
            txt = read_text(p)
            txt = re.sub(r"\n## (Verwandte Bereiche|Related areas).*?(?=\n## )", "\n", txt, flags=re.S)
            blk = "\n" + T["relates"] + "\n" + "".join(
                f"- **{L.get(b,b)}** -> `../{names[b]}/SKILL.md`\n" for b in picks)
            anchor = "## Wenn unklar" if a.lang == "de" else "## If unclear"
            txt = txt.replace(anchor, blk + "\n" + anchor, 1) if anchor in txt else txt.rstrip() + "\n" + blk
            write_text(p, txt); n += 1
    print(f"injected RELATES_TO into {n} wing/room nodes")

# ---------- navigate ----------
def _man(r):
    p = f"{r}/_manifest.json"
    return read_json(p) if os.path.exists(p) else None
def _kids(r):
    m = _man(r); return [s["folder_name"] for s in m["skills"]] if m else []

def cmd_walk(a):
    os.chdir(a.skills_dir)
    def rec(nname, d):
        if is_leaf(nname): print("  " * d + f"- {nname}"); return
        m = _man(nname); k = (m or {}).get("kind", "root" if nname == a.root else "?")
        print("  " * d + f"[{k}] {nname}")
        for c in _kids(nname): rec(c, d + 1)
    rec(a.root, 0)

def cmd_find(a):
    os.chdir(a.skills_dir); term = a.term.lower(); hits = []
    def rec(nname, path):
        path = path + [nname]
        if is_leaf(nname):
            t = read_text(f"{nname}/SKILL.md").lower() if os.path.exists(f"{nname}/SKILL.md") else ""
            if term in nname.lower() or term in t: hits.append(" -> ".join(path))
            return
        for c in _kids(nname): rec(c, path)
    rec(a.root, [])
    print("\n".join(hits) if hits else "Not found")
    if hits: print(f"\n{len(hits)} leaf skill(s) matched.")

def cmd_stats(a):
    os.chdir(a.skills_dir)
    cnt = {"wing":0,"room":0,"zone":0,"station":0}; seen = set()
    def rec(nname):
        if is_leaf(nname): seen.add(nname); return
        m = _man(nname); k = (m or {}).get("kind")
        if k in cnt and nname != a.root: cnt[k] += 1
        for c in _kids(nname): rec(c)
    rec(a.root)
    allleaf = {d for d in os.listdir(".") if is_leaf(d) and not d.startswith("_")}
    print(f"root={a.root}  wings={cnt['wing']} rooms={cnt['room']} zones={cnt['zone']} "
          f"stations={cnt['station']} leaves={len(seen)}  unreached={len(allleaf - seen)}")

# ---------- cli ----------
def main():
    p = argparse.ArgumentParser(prog="skillnav")
    p.add_argument("--skills-dir", required=True)
    p.add_argument("--work", default="/tmp/skillnav")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--include", default=""); b.add_argument("--exclude", default="")
    b.add_argument("--names-file", default="")
    b.add_argument("--model", default="all-MiniLM-L6-v2")
    b.add_argument("--wings", type=int, default=9)
    b.add_argument("--sizes", default="90,30,7"); b.add_argument("--branch", default="8,8,12")
    b.add_argument("--stop", default="")
    b.set_defaults(fn=cmd_build)
    e = sub.add_parser("emit"); e.add_argument("--batch-size", type=int, default=40); e.set_defaults(fn=cmd_emit)
    r = sub.add_parser("render"); r.add_argument("--root", default="navigator"); r.add_argument("--title", default="")
    r.add_argument("--lang", default="de", choices=["de","en"]); r.add_argument("--apply", action="store_true")
    r.set_defaults(fn=cmd_render)
    rl = sub.add_parser("relates"); rl.add_argument("--lang", default="de", choices=["de","en"]); rl.set_defaults(fn=cmd_relates)
    w = sub.add_parser("walk"); w.add_argument("--root", default="navigator"); w.set_defaults(fn=cmd_walk)
    f = sub.add_parser("find"); f.add_argument("term"); f.add_argument("--root", default="navigator"); f.set_defaults(fn=cmd_find)
    s = sub.add_parser("stats"); s.add_argument("--root", default="navigator"); s.set_defaults(fn=cmd_stats)
    a = p.parse_args(); a.fn(a)

if __name__ == "__main__":
    main()
