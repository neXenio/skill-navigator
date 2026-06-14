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

Turns a skill directory into a navigable **decision tree** with a single root entry
skill. Mirrors a memory-palace hierarchy: **Wing (domain) → Room (subdomain) → Zone (topic
cluster) → Station (group of ~7 leaves) → leaf skill**. Each internal node's body is a
*decision node*: a routing question + per-branch keyword hints + relative links to children.

## When to use
- A skills directory has dozens to thousands of `SKILL.md`-based skills.
- Flat description-routing is unreliable; you want guided drill-down.
- You want to navigate a *subset* by glob or name list.

## Requirements
- A Python with `sentence-transformers`, `scikit-learn`, `numpy`.
- The embedding model `all-MiniLM-L6-v2` (auto-downloaded once; ~80MB).

## Install as a plugin

Claude Code can install this repo as a marketplace:

```
claude plugin marketplace add neXenio/skill-navigator
claude plugin install skill-navigator@skill-navigator
```

Codex can install the same repository as a Git marketplace:

```
codex plugin marketplace add neXenio/skill-navigator
codex plugin add skill-navigator@skill-navigator
```

## Run the CLI with uvx

```
uvx --from git+https://github.com/neXenio/skill-navigator skillnav --help
```

## Example use

If your skills live in `~/agent-skills`, build a navigator with:

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

Invoke `team-navigator` in your agent. The agent follows the linked child
`SKILL.md` files until it reaches the matching leaf skill.

## Install from a clone

```
git clone https://github.com/neXenio/skill-navigator.git
cd skill-navigator
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Apply to a skills directory

Point the CLI at the directory that contains your existing skill folders. Each leaf skill must
be a directory with a `SKILL.md` file. Generated navigator nodes are written into the same
skills directory.

Use a scratch directory for build artifacts. Keep it outside the target skills directory.

## Workflow (run from this plugin's `scripts/`)

Let `PY` = a python with the deps, `DIR` = the target skills dir, `WORK` = scratch dir.

**1. Build the tree** (embed + cluster, caps by construction; no LLM):
```
$PY skillnav.py --skills-dir "$DIR" --work "$WORK" build \
    --wings 9 --sizes 90,30,7 --branch 8,8,12 \
    [--include "agb-*,ds-*"] [--exclude "_*,wing-*"] [--names-file subset.txt] \
    [--stop "skill,nutzen,pruefen,dsgvo,bgb"]
```
Tune `--wings` for cleaner top domains; `--sizes` = target leaves per child at depth
wing/room/zone (last value ≈ leaves per station). Check the printed station min/med/max.

**2. Emit label batches**:
```
$PY skillnav.py --skills-dir "$DIR" --work "$WORK" emit --batch-size 40
```
Writes `$WORK/labels_in/batch_NN.json`.

**3. Label every node with an LLM.** For each `labels_in/batch_NN.json`, dispatch a low-cost
labeling job. Each job reads its batch and writes
`$WORK/labels_out/batch_NN.json` as `{node_id: "Label"}`. Prompt template:

> Read `$WORK/labels_in/batch_NN.json` with nodes `{id, level, terms, samples, n}`. For each,
> produce a concise label in **<LANGUAGE>**: wing 1-2 words, room 2-3, zone 2-4, station 2-5
> (more specific deeper). Derive from `terms` + `samples` (folder-names encode the topic).
> Station labels may add identifiers/anchors. FORBIDDEN: generic catch-alls
> (Sonstiges/Allgemein/Misc/Other/cluster), bare numbers, quotes. Write ONLY
> `{id:"Label",...}` to `$WORK/labels_out/batch_NN.json`.

If a node is missing after labeling, drop one fallback file
`$WORK/labels_out/batch_fix.json` with `{id:"Label"}` from its terms.

**4. Render** (dry-run first to confirm `missing=0`, then `--apply`):
```
$PY skillnav.py --skills-dir "$DIR" --work "$WORK" render --root navigator --lang de
$PY skillnav.py --skills-dir "$DIR" --work "$WORK" render --root navigator --lang de --apply
```
`--apply` deletes prior navigator nodes (marked `navigator:true`) and writes the tree +
root. Your real skills and other routers are untouched.

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
`stats` must show `unreached=0`. `find` prints the full `navigator → wing → … → leaf` path.

## Run as a user

After `render --apply`, the target skills directory contains a new root skill, named
`navigator` in the examples above. Invoke that skill in your agent environment, then answer
the routing question at each level. The agent follows the linked child `SKILL.md` files until
it reaches the leaf skill that matches the request.

## Re-running
Idempotent: re-run build→…→render --apply to rebuild from scratch (old navigator nodes are
replaced). Re-run `relates` after render (it re-strips its own block). To re-tune, change
`--wings`/`--sizes` and repeat.

## Notes
- A leaf = skill dir with `SKILL.md` and no `_manifest.json`. Navigator nodes carry
  `_manifest.json` with `"navigator": true` and `kind` ∈ {root,wing,room,zone,station}.
- **The root is auto-discoverable** (`user-invokable: true`). All wing/room/zone/station
  nodes are references (`user-invokable: false`): agents reach them by reading
  `../<name>/SKILL.md` during traversal. The skill list shows one entry: the root.
- `--lang de|en` switches node-body wording.
- Capacity caps (≈7 leaves/station) are soft; large semantic clusters may exceed them.
