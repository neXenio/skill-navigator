#!/usr/bin/env bash
# Build a reference-only skill-navigator over Klotzkette/claude-fuer-deutsches-recht.
#
#   clone upstream  ->  build/emit/label/render  ->  relink leaves to upstream URLs
#   ->  strip upstream leaf dirs  ->  export navigator-only tree.
#
# The exported tree references upstream skills by URL; it copies none of them.
#
# Usage:  bash build.sh [SKILLNAV_PY]
# Env:    DISCOVER(tree|flat) LAYOUT(nested|flat) NAVLANG(de|en) WINGS ROOT WORKROOT EXPORT PY
set -euo pipefail

REPO_URL="https://github.com/Klotzkette/claude-fuer-deutsches-recht.git"
REPO_BASE="https://github.com/Klotzkette/claude-fuer-deutsches-recht/tree/main"
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILLNAV="${1:-$HERE/../../scripts/skillnav.py}"
PY="${PY:-python3}"

WORKROOT="${WORKROOT:-/tmp/skillnav-recht}"
CLONE="$WORKROOT/repo"            # full upstream checkout (skills dir)
WORK="$WORKROOT/work"             # scratch build artifacts
EXPORT="${EXPORT:-$HERE/navigator-generated}"  # reference-only output tree
ROOT="${ROOT:-recht-navigator}"
NAVLANG="${NAVLANG:-de}"
WINGS="${WINGS:-12}"
STOP="${STOP:-skill,recht,nutzen,pruefen,dsgvo,bgb,paragraph,deutsch}"
# Upstream nests all SKILL.md at <plugin>/skills/<skill>/SKILL.md (depth 4).
#   tree -> each top-level plugin = ONE leaf (~230 leaves, fast)
#   flat -> every nested skill = a leaf (~25,672 leaves, full resort, slow embed)
DISCOVER="${DISCOVER:-tree}"
# nested: generated nodes mirror the tree on disk (root/wing/room/.../SKILL.md).
# flat:   all nodes are top-level sibling dirs (marketplace-safe). Set LAYOUT=flat
#         to disable nesting, e.g. when a marketplace updater expects flat skills.
LAYOUT="${LAYOUT:-nested}"
# SLICE=1 prunes the exported tree to ONE representative root->wing->room->station
# path (keeps the committed example small). SLICE=0 keeps the full tree.
SLICE="${SLICE:-1}"

echo "== 1. clone upstream (shallow) =="
mkdir -p "$WORKROOT"
if [ ! -d "$CLONE/.git" ]; then
  git clone --depth 1 "$REPO_URL" "$CLONE"
else
  git -C "$CLONE" pull --ff-only
fi

DIR="$CLONE"   # repo root; --discover handles the nested skill trees
echo "skills-dir = $DIR  (discover=$DISCOVER)"

echo "== 2. build =="
"$PY" "$SKILLNAV" --skills-dir "$DIR" --work "$WORK" build --wings "$WINGS" --stop "$STOP" --discover "$DISCOVER"

echo "== 3. emit label batches =="
"$PY" "$SKILLNAV" --skills-dir "$DIR" --work "$WORK" emit --batch-size 40

echo "== 4. label (deterministic placeholder: distinct terms -> Title Case) =="
echo "   NOTE: replace with an LLM labeling pass for production-quality node names."
"$PY" - "$WORK" <<'PYEOF'
import json, os, sys, glob
work = sys.argv[1]
os.makedirs(f"{work}/labels_out", exist_ok=True)
# Collect every node first so labels can be made globally distinct: when two
# clusters share a top term we extend with the next term instead of appending a
# bare number (avoids "pruefer" / "pruefer-2" sibling wings).
recs = []
for fp in sorted(glob.glob(f"{work}/labels_in/*.json")):
    recs += [(os.path.basename(fp), r) for r in json.load(open(fp, encoding="utf-8"))]
order = {"wing": 0, "room": 1, "zone": 2, "station": 3}
recs.sort(key=lambda x: (order.get(x[1]["level"], 9), x[1]["id"]))
base_n = {"wing": 2, "room": 3, "zone": 3, "station": 4}
out_by_file, used = {}, set()
for fname, rec in recs:
    terms = [t for t in (rec.get("terms") or []) if t]
    n0 = base_n.get(rec["level"], 2)
    lab = None
    for n in range(min(n0, len(terms) or 1), len(terms) + 1):   # grow until distinct
        cand = " ".join(t.capitalize() for t in terms[:n])
        if cand and cand not in used:
            lab = cand; break
    if not lab:                                                 # all terms identical: last resort
        cand = " ".join(t.capitalize() for t in terms[:n0]) or rec["id"]; k = 2
        lab = cand
        while lab in used: lab = f"{cand} {k}"; k += 1
    used.add(lab)
    out_by_file.setdefault(fname, {})[rec["id"]] = lab
for fname, d in out_by_file.items():
    json.dump(d, open(f"{work}/labels_out/{fname}", "w", encoding="utf-8"), ensure_ascii=False)
print(f"wrote {len(used)} distinct placeholder labels")
PYEOF

echo "== 5. render --apply =="
"$PY" "$SKILLNAV" --skills-dir "$DIR" --work "$WORK" render --root "$ROOT" --lang "$NAVLANG" --layout "$LAYOUT"          # dry-run, expect missing=0
"$PY" "$SKILLNAV" --skills-dir "$DIR" --work "$WORK" render --root "$ROOT" --lang "$NAVLANG" --layout "$LAYOUT" --apply
"$PY" "$SKILLNAV" --skills-dir "$DIR" --work "$WORK" relates --lang "$NAVLANG" || true
"$PY" "$SKILLNAV" --skills-dir "$DIR" --work "$WORK" stats --root "$ROOT"

echo "== 6. relink leaves -> upstream URLs + export navigator-only tree =="
"$PY" - "$DIR" "$WORK" "$EXPORT" "$REPO_BASE" <<'PYEOF'
import os, re, sys, json, shutil
DIR, WORK, EXPORT, BASE = sys.argv[1:5]
# nav node paths (relative to skills-dir), works for flat and nested layouts.
names = json.load(open(os.path.join(WORK, "names.json"), encoding="utf-8"))
navpaths = set(v for k, v in names.items())            # includes the root
tops = sorted({p.split("/")[0] for p in navpaths})     # top-level dirs to copy

if os.path.isdir(EXPORT): shutil.rmtree(EXPORT)
os.makedirs(EXPORT)
for d in tops:
    shutil.copytree(os.path.join(DIR, d), os.path.join(EXPORT, d))

# rewrite every link: internal nav link -> keep; anything resolving outside the
# nav tree is a leaf skill -> replace with its upstream URL (nothing copied).
link = re.compile(r'`([^`]+?)/SKILL\.md`')
copied = 0
for cur, _, files in os.walk(EXPORT):
    if "SKILL.md" not in files: continue
    fp = os.path.join(cur, "SKILL.md")
    rel_dir = os.path.relpath(cur, EXPORT)            # = node path relative to skills-dir
    def repl(m):
        target = os.path.normpath(os.path.join(rel_dir, m.group(1)))
        if target in navpaths:                        # internal navigator link
            return m.group(0)
        return f"`{BASE}/{target}`"                   # leaf -> upstream URL
    txt = open(fp, encoding="utf-8").read()
    open(fp, "w", encoding="utf-8").write(link.sub(repl, txt))
    copied += 1
print(f"exported {copied} navigator nodes to {EXPORT} "
      f"(layout-agnostic, leaves -> upstream URLs, none copied)")
PYEOF

if [ "$SLICE" = "1" ]; then
echo "== 7. prune to one representative path (SLICE=1) =="
"$PY" - "$EXPORT" "$ROOT" <<'PYEOF'
import os, re, json, shutil, sys
EXPORT, ROOT = sys.argv[1:3]
def navchildren(p):
    return [d for d in sorted(os.listdir(p)) if os.path.isdir(os.path.join(p, d))
            and os.path.exists(os.path.join(p, d, "_manifest.json"))]
root = os.path.join(EXPORT, ROOT)
chosen = None
for w in navchildren(root):                       # pick wing -> room -> station
    for r in navchildren(os.path.join(root, w)):
        st = navchildren(os.path.join(root, w, r))
        if st: chosen = (w, r, st[0]); break
    if chosen: break
if not chosen:
    print("no wing->room->station path; leaving full tree"); sys.exit(0)
w, r, s = chosen
keep = {root: w, os.path.join(root, w): r, os.path.join(root, w, r): s,
        os.path.join(root, w, r, s): None}
for node, k in keep.items():
    for c in navchildren(node):
        if c != k: shutil.rmtree(os.path.join(node, c))
def keep_only_child(node, child):
    sp = os.path.join(node, "SKILL.md"); t = open(sp, encoding="utf-8").read()
    out = [ln for ln in t.split("\n")
           if not (re.match(r'\s*-\s+\*\*', ln) and "/SKILL.md`" in ln) or f"{child}/SKILL.md`" in ln]
    t = "\n".join(out)
    t = re.sub(r"\n## (Verwandte Bereiche|Related areas).*?(?=\n## )", "\n", t, flags=re.S)
    t = re.sub(r"(Routes to 1 of|Leitet zu 1 von) \d+( Unterskills)?",
               lambda m: ("Routes to 1 of 1" if "Routes" in m.group(1) else "Leitet zu 1 von 1 Unterskills"), t)
    open(sp, "w", encoding="utf-8").write(t)
    mp = os.path.join(node, "_manifest.json"); m = json.load(open(mp, encoding="utf-8"))
    m["skills"] = [x for x in m["skills"] if os.path.basename(x["folder_name"]) == child]
    json.dump(m, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
keep_only_child(root, w); keep_only_child(os.path.join(root, w), r); keep_only_child(os.path.join(root, w, r), s)
print(f"pruned to: {ROOT}/{w}/{r}/{s}")
PYEOF
fi

echo "== done =="
echo "navigator-only tree: $EXPORT"
