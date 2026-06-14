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
    if not os.path.exists(p):
        # tree-as-leaf: the plugin dir may have no own SKILL.md. Fall back to its
        # README, else the first nested SKILL.md, so the leaf still embeds well.
        if os.path.exists(f"{folder}/README.md"):
            txt = read_text(f"{folder}/README.md")
            txt = re.sub(r'<!--.*?-->', ' ', txt, flags=re.S)      # drop HTML comments
            txt = re.sub(r'^\s*#+\s*', '', txt, flags=re.M)        # drop markdown headers
            txt = re.sub(r'[`*_>|\-]+', ' ', txt)                  # drop md punctuation
            return re.sub(r'\s+', ' ', txt).strip()[:300]
        for cur, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if d != ".git"]
            if "SKILL.md" in files:
                p = os.path.join(cur, "SKILL.md"); break
        else:
            return ""
    t = read_text(p)
    m = re.search(r'description:\s*[>|]?\s*\n?(.*?)(?:\nuser-invokable:|\nargs:|\nmetadata:|\ndisable|\n---)', t, re.S)
    if not m:
        m = re.search(r'description:\s*(.+)', t)
        return m.group(1).strip() if m else ""
    return re.sub(r'\s+', ' ', m.group(1)).strip()

def is_leaf(d):
    return os.path.isdir(d) and os.path.exists(f"{d}/SKILL.md") and not os.path.exists(f"{d}/_manifest.json")

def _has_skill_anywhere(d):
    for cur, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if x != ".git"]
        if "SKILL.md" in files and not os.path.exists(os.path.join(cur, "_manifest.json")):
            return True
    return False

def find_leaves(include, exclude, discover="top"):
    # discover modes for trees of skills:
    #   top  -> top-level dirs that directly contain SKILL.md (default, flat dirs)
    #   tree -> each top-level dir that contains a SKILL.md anywhere = ONE leaf
    #   flat -> every dir with SKILL.md at any depth = a leaf (id is its relpath)
    out = []
    if discover == "flat":
        for cur, dirs, files in os.walk("."):
            dirs[:] = [x for x in dirs if x != ".git" and not x.startswith("_")]
            if "SKILL.md" in files and not os.path.exists(os.path.join(cur, "_manifest.json")):
                rel = os.path.relpath(cur, ".")
                if rel != ".":
                    out.append(rel)
        out.sort()
    else:
        for d in sorted(os.listdir(".")):
            if d.startswith("_") or not os.path.isdir(d):
                continue
            ok = is_leaf(d) if discover == "top" else _has_skill_anywhere(d)
            if ok:
                out.append(d)
    def keep(p):
        b = os.path.basename(p)
        if include and not any(fnmatch.fnmatch(b, g) or fnmatch.fnmatch(p, g) for g in include):
            return False
        if exclude and any(fnmatch.fnmatch(b, g) or fnmatch.fnmatch(p, g) for g in exclude):
            return False
        return True
    return [p for p in out if keep(p)]

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
   "frage": "## Frage\n\nWaehle den passenden Unterbereich von «{title}». Lade dessen SKILL.md; weiter bis zum Blatt (Einzelskill).\n\n## Zweige",
   "branch": "- **{lb}**: Stichworte: {hint} -> `{t}`",
   "leaf_head": "## Einzelskills (Blaetter)\n\nWaehle das passende Einzelskill; lade dessen Anweisungen. Unterste Ebene.",
   "leaf_branch": "- **{lb}**: {hint} -> `{t}`",
   "unclear": "## Wenn unklar\n- Mehrere passen -> nenne Kandidaten, frage Nutzer.\n- Keiner passt -> gehe HOCH (Link «Eine Ebene hoeher») und nimm einen Nachbarzweig. Erst an der Wurzel den Nutzer um Praezisierung bitten.",
   "relates": "## Verwandte Bereiche (RELATES_TO)\n\nSemantisch nahe Bereiche in anderen Zweigen. Bei Grenzfaellen dort weitersuchen:",
   "routes": "Leitet zu 1 von {n} Unterskills. Lies das gewaehlte Unterskill vollstaendig, bevor du handelst.",
   "up": "## Eine Ebene hoeher\n\nPasst kein Zweig? Gehe zurueck zu: `{p}`",
 },
 "en": {
   "level": {"wing":"Area","room":"Sub-area","zone":"Topic zone","station":"Topic station"},
   "node_title": "Decision node",
   "frage": "## Question\n\nPick the part of «{title}» matching the request. Load its SKILL.md; continue to a leaf.\n\n## Branches",
   "branch": "- **{lb}**: keywords: {hint} -> `{t}`",
   "leaf_head": "## Leaf skills\n\nPick the matching leaf; load its instructions.",
   "leaf_branch": "- **{lb}**: {hint} -> `{t}`",
   "unclear": "## If unclear\n- Several fit -> name candidates, ask user.\n- None fit -> go UP (the «Up one level» link) and try a sibling. Only at the root, ask the user to narrow.",
   "relates": "## Related areas (RELATES_TO)\n\nClose areas in other branches. Follow them for borderline cases:",
   "routes": "Route to 1 of {n} sub-skills. Read the chosen one fully before acting.",
   "up": "## Up one level\n\nNo branch fits? Go back to: `{p}`",
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
    leaves = find_leaves(include, exclude, a.discover)
    if a.names_file:
        keep = set(l.strip() for l in read_text(a.names_file).splitlines() if l.strip())
        leaves = [l for l in leaves if l in keep]
    print(f"leaves: {len(leaves)}")
    if len(leaves) < 8: sys.exit("need >=8 leaves to build a tree")
    descs = {l: desc_of(l) for l in leaves}
    texts = [f"{l.replace('/',' ').replace('-',' ')}: {descs[l][:150]}" for l in leaves]
    print(f"embedding with {a.model} ...")
    emb = normalize(SentenceTransformer(a.model).encode(texts, batch_size=64, show_progress_bar=False))

    GENERIC = set(a.stop.split(",")) if a.stop else set()
    name_docs = [" ".join(t for t in re.split(r'[-/]', l) if len(t) >= 4 and t not in GENERIC) for l in leaves]
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
        # small enough to be a leaf-holder directly (splitting it would spawn tiny
        # 1-2 leaf children). Keeps holders >= min_leaves and nodes >= min_children.
        if depth == len(LEVELS) - 1 or len(idx) < max(2 * a.min_leaves, a.min_children):
            nodes[nid]["leaves"] = [leaves[i] for i in idx]; return nid
        k = min(BRANCH[depth], math.ceil(len(idx) / SIZE[depth]))
        k = max(a.min_children, k); k = min(k, len(idx))
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

    # ---- rebalance: no 1-child chains, no tiny leaf-holders, >= min_children per node ----
    lidx = {l: i for i, l in enumerate(leaves)}
    def nleaves(nid):
        n = nodes[nid]
        if n["leaves"]: return n["leaves"]
        out = []
        for c in n["children"]: out += nleaves(c)
        return out
    def cent(nid):
        ms = [lidx[l] for l in nleaves(nid) if l in lidx]
        v = emb[ms].mean(0); return v / (np.linalg.norm(v) + 1e-9)
    def attach(nid, l):                       # push a leaf down to the most-similar leaf-holder
        n = nodes[nid]
        if n["leaves"]: n["leaves"].append(l); return
        if not n["children"]: n["leaves"].append(l); return
        best = max(n["children"], key=lambda c: float(cent(c) @ emb[lidx[l]]))
        attach(best, l)
    def siblings(nid):
        p = nodes[nid]["parent"]
        return roots if p == "ROOT" else nodes[p]["children"]
    def drop(nid):
        s = siblings(nid)
        if nid in s: s.remove(nid)
        del nodes[nid]
    def is_holder(nid): return bool(nodes[nid]["leaves"])

    def rebalance_children(clist, owner):       # owner: a node id or "ROOT"
        changed = True
        while changed:
            changed = False
            for c in list(clist):               # collapse single-child / empty internal children
                cn = nodes[c]
                if not cn["leaves"] and len(cn["children"]) == 1:
                    g = cn["children"][0]; nodes[g]["parent"] = owner
                    clist[clist.index(c)] = g; del nodes[c]; changed = True
                elif not cn["leaves"] and not cn["children"]:
                    clist.remove(c); del nodes[c]; changed = True
        if len(clist) > 1:                      # dissolve undersized leaf-holders into best sibling
            for c in list(clist):
                if is_holder(c) and len(nodes[c]["leaves"]) < a.min_leaves and len(clist) > 1:
                    sibs = [s for s in clist if s != c]
                    for l in list(nodes[c]["leaves"]):
                        attach(max(sibs, key=lambda s: float(cent(s) @ emb[lidx[l]])), l)
                    drop(c)
        for c in list(clist):                   # lift internal children that stayed below min_children
            cn = nodes[c]
            if not is_holder(c) and 1 < len(cn["children"]) < a.min_children:
                for g in cn["children"]: nodes[g]["parent"] = owner
                clist[clist.index(c):clist.index(c)+1] = cn["children"]; del nodes[c]

    def fix(nid):
        n = nodes[nid]
        for c in list(n["children"]): fix(c)
        if not is_holder(nid): rebalance_children(n["children"], nid)
    for r in list(roots): fix(r)
    rebalance_children(roots, "ROOT")

    LV = ["wing", "room", "zone", "station"]    # recompute level by depth after restructuring
    def setlvl(nid, d):
        nodes[nid]["level"] = LV[min(d, len(LV) - 1)]
        for c in nodes[nid]["children"]: setlvl(c, d + 1)
    for r in roots: setlvl(r, 0)

    write_json(f"{a.work}/tree.json", {"root_children": roots, "nodes": nodes}, ensure_ascii=False)
    np.save(f"{a.work}/emb.npy", emb)
    write_json(f"{a.work}/leaves.json", leaves)
    from collections import Counter
    lvl = Counter(n["level"] for n in nodes.values())
    sizes = [len(n["leaves"]) for n in nodes.values() if n["leaves"]]
    kids = [len(n["children"]) for n in nodes.values() if n["children"]]
    print("levels:", dict(lvl), "| leaf-holders:", len(sizes),
          "leaf/holder min/med/max:", min(sizes), int(np.median(sizes)), max(sizes),
          "| children/node min/med/max:", min(kids), int(np.median(kids)), max(kids))
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
    dirn = {}                                   # globally-unique basename per node
    for nid, n in nodes.items():
        base = f"{PRE[n['level']]}-{slug(L.get(nid, nid))}"; nm = base; k = 2
        while nm in used: nm = f"{base}-{k}"; k += 1
        used.add(nm); dirn[nid] = nm
    label = lambda i: L.get(i, i)
    hint = lambda i: ", ".join(nodes[i]["terms"][:5]) or "-"

    nested = (a.layout == "nested")
    pathmemo = {}
    def npath(nid):                             # on-disk path of a node, relative to skills-dir
        if not nested: return dirn[nid]         # flat: every node is a top-level sibling
        if nid in pathmemo: return pathmemo[nid]
        p = nodes[nid]["parent"]
        pp = a.root if p == "ROOT" else npath(p)
        pathmemo[nid] = f"{pp}/{dirn[nid]}"; return pathmemo[nid]
    def nlink(to_path, from_path):              # relative SKILL.md link between two node dirs
        return os.path.relpath(to_path, from_path) + "/SKILL.md"

    def dedup(cids):
        seen = {}; out = {}
        for c in cids:
            lb = label(c); b = lb; k = 2
            while lb in seen: lb = f"{b} ({k})"; k += 1
            seen[lb] = 1; out[c] = lb
        return out

    def write(nodepath, name, lvl, title, dsc, branches, leafmode, is_root=False, parent_path=None):
        # branches: list of (display_label, hint, target_path-relative-to-skills-dir)
        skills = [{"name": os.path.basename(tp), "folder_name": tp, "description_at_merge": ""}
                  for _, _, tp in branches]
        man = {"router_name": name, "skills_dir": a.skills_dir, "created": now(),
               "kind": "root" if is_root else lvl, "navigator": True, "root": is_root,
               "layout": a.layout, "skills": skills}
        if not a.apply: return
        os.makedirs(nodepath, exist_ok=True)
        write_json(f"{nodepath}/_manifest.json", man, ensure_ascii=False, indent=1)
        brl = [(lb, h, nlink(tp, nodepath)) for lb, h, tp in branches]
        if leafmode:
            head = T["leaf_head"]; bl = "\n".join(T["leaf_branch"].format(lb=lb, hint=h, t=t_) for lb, h, t_ in brl)
        else:
            head = T["frage"].format(title=title); bl = "\n".join(T["branch"].format(lb=lb, hint=h, t=t_) for lb, h, t_ in brl)
        avail = ", ".join(f'"{os.path.basename(tp)}"' for _, _, tp in branches)
        up = T["up"].format(p=nlink(parent_path, nodepath)) + "\n\n" if parent_path is not None else ""
        # Root is user-invokable/auto-discoverable. Sub-nodes are referenced by their
        # relative SKILL.md link during traversal and stay out of the skill list.
        body = (f"---\nname: {name}\ndescription: >\n  {dsc}\n"
                f"user-invokable: {'true' if is_root else 'false'}\n"
                f"args:\n  - name: skill\n    description: >\n      Direct sub-skill to load. Available: {avail}.\n    required: false\n"
                f"metadata:\n  category: \"router\"\n  kind: \"{'root' if is_root else lvl}\"\n  navigator: \"true\"\n---\n\n"
                f"# {T['node_title']}: {title}  ({T['level'][lvl]})\n\n{T['routes'].format(n=len(branches))}\n\n"
                f"{head}\n{bl}\n\n{up}{T['unclear']}\n")
        write_text(f"{nodepath}/SKILL.md", body)

    if a.apply:
        old = [d for d in os.listdir(".") if os.path.isdir(d) and os.path.exists(f"{d}/_manifest.json")
               and read_json(f"{d}/_manifest.json").get("navigator") and not d.startswith("_")]
        for d in old: shutil.rmtree(d)
        print(f"deleted {len(old)} old navigator nodes")

    nw = 0
    for nid, n in nodes.items():
        lvl = n["level"]; ttl = label(nid); np_ = npath(nid)
        pp = a.root if n["parent"] == "ROOT" else npath(n["parent"])
        if n["leaves"]:   # leaf-holder (station, or an intermediate node that bottomed out early)
            br = []
            for l in n["leaves"]:
                d = desc_of(l)[:110]
                br.append((os.path.basename(l).replace("-", " "), d or "leaf skill", l))
            dsc = (f"{T['node_title']} ({T['level'][lvl]}) {ttl}: {len(n['leaves'])} leaf skills.")[:1020]
            write(np_, dirn[nid], lvl, ttl, dsc, br, True, parent_path=pp)
        else:
            cids = n["children"]; disp = dedup(cids)
            br = [(disp[c], hint(c), npath(c)) for c in cids]
            dsc = (f"{T['node_title']} ({T['level'][lvl]}) {ttl} -> {', '.join(disp[c] for c in cids)}.")[:1020]
            write(np_, dirn[nid], lvl, ttl, dsc, br, False, parent_path=pp)
        nw += 1
    # root
    rc = t["root_children"]; disp = dedup(rc)
    br = [(disp[c], hint(c), npath(c)) for c in rc]
    rdesc = (f"{a.root}: decision-tree entry point. Top areas: {', '.join(disp[c] for c in rc)}. "
             "Answer the question, pick an area, load its SKILL.md, navigate down to the matching leaf skill.")[:1020]
    write(a.root, a.root, "wing", a.title or a.root, rdesc, br, False, is_root=True)
    namemap = {nid: npath(nid) for nid in nodes}; namemap["ROOT"] = a.root
    write_json(f"{a.work}/names.json", namemap, ensure_ascii=False)
    print(f"internal nodes: {nw} + root '{a.root}'  (layout={a.layout}, APPLY={a.apply})")

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
        if n["leaves"]: return n["leaves"]
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
                f"- **{L.get(b,b)}** -> `{os.path.relpath(names[b], names[aid])}/SKILL.md`\n" for b in picks)
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
def _is_nav(r):
    # a navigator internal node = a dir carrying a navigator manifest. Anything a
    # node links that lacks one is a leaf skill (works for nested tree/flat leaves
    # whose folder has no direct SKILL.md).
    m = _man(r); return bool(m and m.get("navigator"))

def cmd_walk(a):
    os.chdir(a.skills_dir)
    def rec(nname, d):
        if not _is_nav(nname): print("  " * d + f"- {nname}"); return
        k = _man(nname).get("kind", "root" if nname == a.root else "?")
        print("  " * d + f"[{k}] {nname}")
        for c in _kids(nname): rec(c, d + 1)
    rec(a.root, 0)

def cmd_find(a):
    os.chdir(a.skills_dir); term = a.term.lower(); hits = []
    def rec(nname, path):
        path = path + [nname]
        if not _is_nav(nname):
            t = read_text(f"{nname}/SKILL.md").lower() if os.path.exists(f"{nname}/SKILL.md") else ""
            if term in nname.lower() or term in t: hits.append(" -> ".join(path))
            return
        for c in _kids(nname): rec(c, path)
    rec(a.root, [])
    print("\n".join(hits) if hits else "Not found")
    if hits: print(f"\n{len(hits)} leaf skill(s) matched.")

def cmd_stats(a):
    os.chdir(a.skills_dir)
    cnt = {"wing":0,"room":0,"zone":0,"station":0}; leaves = set(); visited = set()
    def rec(nname):
        if not _is_nav(nname): leaves.add(nname); return
        visited.add(nname)
        k = _man(nname).get("kind")
        if k in cnt and nname != a.root: cnt[k] += 1
        for c in _kids(nname): rec(c)
    rec(a.root)
    allnav = {d for d in os.listdir(".") if not d.startswith("_") and _is_nav(d)}
    print(f"root={a.root}  wings={cnt['wing']} rooms={cnt['room']} zones={cnt['zone']} "
          f"stations={cnt['station']} leaves={len(leaves)}  unreached={len(allnav - visited)}")

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
    b.add_argument("--discover", default="top", choices=["top", "tree", "flat"],
                   help="top: top-level dirs with SKILL.md; tree: each top-level skill-tree = one leaf; flat: every SKILL.md dir at any depth")
    b.add_argument("--min-children", type=int, default=3,
                   help="rebalance: collapse 1-child chains and flatten so each internal node has >= this many children")
    b.add_argument("--min-leaves", type=int, default=3,
                   help="rebalance: dissolve leaf-holders with fewer leaves into the nearest sibling")
    b.set_defaults(fn=cmd_build)
    e = sub.add_parser("emit"); e.add_argument("--batch-size", type=int, default=40); e.set_defaults(fn=cmd_emit)
    r = sub.add_parser("render"); r.add_argument("--root", default="navigator"); r.add_argument("--title", default="")
    r.add_argument("--lang", default="en", choices=["de","en"]); r.add_argument("--apply", action="store_true")
    r.add_argument("--layout", default="flat", choices=["flat","nested"],
                   help="flat: all nodes as top-level sibling dirs (marketplace-safe, default). nested: nodes mirror the tree on disk under the root dir")
    r.set_defaults(fn=cmd_render)
    rl = sub.add_parser("relates"); rl.add_argument("--lang", default="en", choices=["de","en"]); rl.set_defaults(fn=cmd_relates)
    w = sub.add_parser("walk"); w.add_argument("--root", default="navigator"); w.set_defaults(fn=cmd_walk)
    f = sub.add_parser("find"); f.add_argument("term"); f.add_argument("--root", default="navigator"); f.set_defaults(fn=cmd_find)
    s = sub.add_parser("stats"); s.add_argument("--root", default="navigator"); s.set_defaults(fn=cmd_stats)
    a = p.parse_args(); a.fn(a)

if __name__ == "__main__":
    main()
