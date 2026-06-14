---
name: skill-navigator
description: >
  Build a decision-tree "navigator" skill over a subset of installed skills. Embeds each
  skill's description, clusters them bottom-up into a 4-tier tree (Wing > Room > Zone >
  Station > leaf), LLM-labels every node, and writes one decision-node SKILL.md per node
  plus a single root entry skill. An agent then enters the root, answers a routing question,
  and follows branch hints down tier by tier until it reaches the right leaf skill. Use when a skills directory has too many skills to route
  by description alone and you want one navigable entry point. NOT for creating new skills,
  installing skills, or grouping 2-3 skills (use a plain router for that).
metadata:
  category: skills-management
---
# skill-navigator

Turns skill directory into navigable **decision tree** with single root entry skill. Mirrors memory-palace hierarchy: **Wing (domain) → Room (subdomain) → Zone (topic cluster) → Station (group of ~7 leaves) → leaf skill**. Each internal node body is *decision node*: routing question + per-branch keyword hints + relative links to children.

## When to use
- Skills directory has dozens to thousands of `SKILL.md` skills.
- Flat description-routing unreliable; want guided drill-down.
- Want navigate *subset* by glob or name list.

## Requirements
- Python with `sentence-transformers`, `scikit-learn`, `numpy`.
- Embedding model `all-MiniLM-L6-v2` (auto-downloaded once; ~80MB).

## Install as a plugin

Claude Code installs this repo as marketplace:

```
claude plugin marketplace add neXenio/skill-navigator
claude plugin install skill-navigator@skill-navigator
```

Codex installs same repo as Git marketplace:

```
codex plugin marketplace add neXenio/skill-navigator
codex plugin add skill-navigator@skill-navigator
```

## Run the CLI with uvx

```
uvx --from git+https://github.com/neXenio/skill-navigator skillnav --help
```

## Example use

Skills live in `~/agent-skills`? Build navigator:

```
DIR=~/agent-skills
WORK=/tmp/skillnav-agent-skills

uvx --from git+https://github.com/neXenio/skill-navigator skillnav --skills-dir "$DIR" --work "$WORK" build --wings 3
uvx --from git+https://github.com/neXenio/skill-navigator skillnav --skills-dir "$DIR" --work "$WORK" emit
```

Label `$WORK/labels_in/*.json` into `$WORK/labels_out/*.json`, then render and verify:

```
uvx --from git+https://github.com/neXenio/skill-navigator skillnav --skills-dir "$DIR" --work "$WORK" render --root team-navigator --lang en --apply
uvx --from git+https://github.com/neXenio/skill-navigator skillnav --skills-dir "$DIR" --work "$WORK" stats --root team-navigator
uvx --from git+https://github.com/neXenio/skill-navigator skillnav --skills-dir "$DIR" --work "$WORK" find "database" --root team-navigator
```

Invoke `team-navigator` in agent. Agent follows linked child `SKILL.md` files until reach matching leaf skill.

## Install from a clone

```
git clone https://github.com/neXenio/skill-navigator.git
cd skill-navigator
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Apply to a skills directory

Point CLI at directory holding existing skill folders. Each leaf skill must be directory with `SKILL.md` file. Generated navigator nodes written into same skills directory.

Use scratch directory for build artifacts. Keep outside target skills directory.

## Workflow (run from this plugin's `scripts/`)

Let `PY` = python with deps, `DIR` = target skills dir, `WORK` = scratch dir.

**1. Build the tree** (embed + cluster, caps by construction; no LLM):
```
$PY skillnav.py --skills-dir "$DIR" --work "$WORK" build \
    --wings 9 --sizes 90,30,7 --branch 8,8,12 \
    [--discover top|tree|flat] [--min-children 3] [--min-leaves 3] \
    [--include "agb-*,ds-*"] [--exclude "_*,wing-*"] [--names-file subset.txt] \
    [--stop "skill,nutzen,pruefen,dsgvo,bgb"]
```
Tune `--wings` for cleaner top domains; `--sizes` = target leaves per child at depth wing/room/zone (last value ≈ leaves per station). After clustering, build **rebalances**: collapses 1-child chains, dissolves leaf-holders below `--min-leaves` into nearest sibling, lifts nodes still below `--min-children`, so every node ends with **≥3 children** and every holder **≥3 leaves**. Check printed `children/node` and `leaf/holder` min/med/max.

`--discover` picks what counts as leaf when skills nested in trees:
- `top` (default): top-level dirs directly holding `SKILL.md` (flat skill dirs).
- `tree`: each top-level dir holding `SKILL.md` *anywhere* is **one** leaf, use for marketplaces whose plugins bundle many skills (`<plugin>/skills/<skill>/SKILL.md`).
- `flat`: every `SKILL.md` dir at any depth is leaf (id = its relpath), resorts whole tree into one fresh navigator. `include`/`exclude` match basename or relpath.

**2. Emit label batches**:
```
$PY skillnav.py --skills-dir "$DIR" --work "$WORK" emit --batch-size 40
```
Writes `$WORK/labels_in/batch_NN.json`.

**3. Label every node with an LLM.** For each `labels_in/batch_NN.json`, dispatch low-cost labeling job. Each job reads its batch, writes `$WORK/labels_out/batch_NN.json` as `{node_id: "Label"}`. Prompt template:

> Read `$WORK/labels_in/batch_NN.json` with nodes `{id, level, terms, samples, n}`. For each, produce a concise label in **<LANGUAGE>**: wing 1-2 words, room 2-3, zone 2-4, station 2-5 (more specific deeper). Derive from `terms` + `samples` (folder-names encode the topic). Station labels may add identifiers/anchors. FORBIDDEN: generic catch-alls (Sonstiges/Allgemein/Misc/Other/cluster), bare numbers, quotes. Write ONLY `{id:"Label",...}` to `$WORK/labels_out/batch_NN.json`.

Node missing after labeling? Drop one fallback file `$WORK/labels_out/batch_fix.json` with `{id:"Label"}` from its terms.

**4. Render** (dry-run first to confirm `missing=0`, then `--apply`):
```
$PY skillnav.py --skills-dir "$DIR" --work "$WORK" render --root navigator [--layout flat|nested]
$PY skillnav.py --skills-dir "$DIR" --work "$WORK" render --root navigator --layout nested --apply
```
`--layout flat` (default) writes every node as top-level sibling dir (marketplace-safe, disable nesting here if marketplace updater expects flat skills). `--layout nested` mirrors tree on disk under root dir. Links relative either way (`os.path.relpath`), each non-root node gets **"Up one level"** backlink so agent backtracks when no branch fits. `--apply` deletes prior navigator nodes (marked `navigator:true`) and writes tree + root. Real skills and other routers untouched.

**5. Inject cross-links** (data-driven RELATES_TO, centroid cosine, cross-branch):
```
$PY skillnav.py --skills-dir "$DIR" --work "$WORK" relates --lang de
```

**6. Verify**:
```
$PY skillnav.py --skills-dir "$DIR" --work "$WORK" stats   --root navigator
$PY skillnav.py --skills-dir "$DIR" --work "$WORK" find "<term>" --root navigator
$PY skillnav.py --skills-dir "$DIR" --work "$WORK" walk   --root navigator | head
```
`stats` must show `unreached=0`. `find` prints full `navigator → wing → … → leaf` path.

## Run as a user

After `render --apply`, target skills directory holds new root skill, named `navigator` in examples above. Invoke that skill in agent environment, answer routing question at each level. Agent follows linked child `SKILL.md` files until reach leaf skill matching request.

## Re-running
Idempotent: re-run build→…→render --apply to rebuild from scratch (old navigator nodes replaced). Re-run `relates` after render (re-strips its own block). To re-tune, change `--wings`/`--sizes` and repeat.

## Notes
- Leaf = skill dir with `SKILL.md` and no `_manifest.json`. Navigator nodes carry `_manifest.json` with `"navigator": true` and `kind` ∈ {root,wing,room,zone,station}.
- **Root auto-discoverable** (`user-invokable: true`). All wing/room/zone/station nodes are references (`user-invokable: false`): agents reach them by reading `../<name>/SKILL.md` during traversal. Skill list shows one entry: the root.
- `--lang de|en` switches node-body wording (default `en`).
- `--layout flat|nested`: flat = top-level sibling dirs (marketplace-safe, default); nested = nodes mirror tree on disk under root.
- Rebalance guarantees ≥`--min-children` per node and ≥`--min-leaves` per holder; capacity caps (`--sizes`/`--branch`) soft, large clusters may exceed.
- Each non-root node has **Up one level** backlink for backtracking.
- Worked example over 25k-skill corpus in [`examples/claude-fuer-deutsches-recht/`](../../examples/claude-fuer-deutsches-recht/README.md).