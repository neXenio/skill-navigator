# skill-navigator

Build a decision-tree navigator over a directory of `SKILL.md`-based skills.
`skill-navigator` gives an agent one root entry skill, then guides it tier by
tier until it reaches the right leaf skill.

Hierarchy: **Wing -> Room -> Zone -> Station -> leaf skill**. Each internal
node is a decision node with a routing question, branch keyword hints, relative
links to children, and `RELATES_TO` cross-links between related branches.

## Features

- Embeds each leaf skill from `folder-name + description`.
- Clusters skills top-down with k-means into a bounded 4-tier tree.
- Emits JSON batches so an LLM workflow can label internal nodes.
- Renders one decision-node `SKILL.md` plus `_manifest.json` per node.
- Marks generated nodes with `"navigator": true`, so rebuilds replace
  navigator-owned directories.
- Provides `walk`, `find`, and `stats` commands for verification.

## Requirements

- Python 3.10+
- `sentence-transformers`
- `scikit-learn`
- `numpy`

## Install as a Plugin

Claude Code can install this repo as a marketplace:

```bash
claude plugin marketplace add neXenio/skill-navigator
claude plugin install skill-navigator@skill-navigator
```

Codex can install the same repository as a Git marketplace:

```bash
codex plugin marketplace add neXenio/skill-navigator
codex plugin add skill-navigator@skill-navigator
```

The installed plugin contributes the `skill-navigator` skill. The CLI still
runs as a separate Python command because it embeds and clusters your local
skills directory.

## Run the CLI with uvx

Use `uvx` when you want the command without cloning the repo:

```bash
uvx --from git+https://github.com/neXenio/skill-navigator skillnav --help
```

Run it against your skills directory:

```bash
DIR=/path/to/skills
WORK=/tmp/skillnav

uvx --from git+https://github.com/neXenio/skill-navigator skillnav --skills-dir "$DIR" --work "$WORK" build --wings 9
uvx --from git+https://github.com/neXenio/skill-navigator skillnav --skills-dir "$DIR" --work "$WORK" emit
# Label $WORK/labels_in/*.json into $WORK/labels_out/*.json.
uvx --from git+https://github.com/neXenio/skill-navigator skillnav --skills-dir "$DIR" --work "$WORK" render --root navigator --lang en --apply
uvx --from git+https://github.com/neXenio/skill-navigator skillnav --skills-dir "$DIR" --work "$WORK" relates --lang en
uvx --from git+https://github.com/neXenio/skill-navigator skillnav --skills-dir "$DIR" --work "$WORK" stats --root navigator
```

## Example Use

Suppose your skills live in `~/agent-skills`:

```text
~/agent-skills/
  api-review/SKILL.md
  bug-triage/SKILL.md
  database-migration/SKILL.md
  dependency-upgrade/SKILL.md
  incident-report/SKILL.md
  performance-audit/SKILL.md
  release-notes/SKILL.md
  test-generation/SKILL.md
```

Build a navigator over those skills:

```bash
DIR=~/agent-skills
WORK=/tmp/skillnav-agent-skills

uvx --from git+https://github.com/neXenio/skill-navigator skillnav --skills-dir "$DIR" --work "$WORK" build --wings 3
uvx --from git+https://github.com/neXenio/skill-navigator skillnav --skills-dir "$DIR" --work "$WORK" emit
```

Label the files in `$WORK/labels_in/` with your preferred LLM workflow and write
matching JSON files into `$WORK/labels_out/`. Then render and verify:

```bash
uvx --from git+https://github.com/neXenio/skill-navigator skillnav --skills-dir "$DIR" --work "$WORK" render --root team-navigator --lang en --apply
uvx --from git+https://github.com/neXenio/skill-navigator skillnav --skills-dir "$DIR" --work "$WORK" stats --root team-navigator
uvx --from git+https://github.com/neXenio/skill-navigator skillnav --skills-dir "$DIR" --work "$WORK" find "database" --root team-navigator
```

Your skills directory now includes generated navigator folders, for example:

```text
~/agent-skills/
  team-navigator/SKILL.md
  wing-platform/SKILL.md
  stn-database-work/SKILL.md
  api-review/SKILL.md
  database-migration/SKILL.md
  ...
```

In your agent, invoke `team-navigator`. The agent reads its branch list, follows
the linked child `SKILL.md` files, and ends at the matching leaf skill.

## Install from a Clone

```bash
git clone https://github.com/neXenio/skill-navigator.git
cd skill-navigator
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Apply to a Skills Directory

Point the CLI at the directory that contains your existing skill folders. Each
leaf skill must be a directory with a `SKILL.md` file. Generated navigator nodes
are written into the same skills directory.

Use a scratch directory for build artifacts:

```bash
PY=.venv/bin/python
DIR=/path/to/skills
WORK=/tmp/skillnav

$PY scripts/skillnav.py --skills-dir "$DIR" --work "$WORK" build --wings 9
$PY scripts/skillnav.py --skills-dir "$DIR" --work "$WORK" emit
# Label $WORK/labels_in/*.json into $WORK/labels_out/*.json.
$PY scripts/skillnav.py --skills-dir "$DIR" --work "$WORK" render --root navigator --lang en --apply
$PY scripts/skillnav.py --skills-dir "$DIR" --work "$WORK" relates --lang en
$PY scripts/skillnav.py --skills-dir "$DIR" --work "$WORK" stats --root navigator
```

The generated root skill is user-invokable. Agents reach generated wing, room,
zone, and station reference nodes by reading child `SKILL.md` files during traversal.

## Run as a User

After `render --apply`, your skills directory contains a new root skill, named
`navigator` in the example above. Invoke that skill in your agent environment,
then answer the routing question at each level. The agent follows the linked
child `SKILL.md` files until it reaches the leaf skill that matches the request.

To rebuild, rerun the same command sequence. `render --apply` replaces previous
navigator-generated directories and keeps source skills untouched.

## Commands

- `build`: embed leaf skills and create the tree.
- `emit`: write node-labeling batches into `$WORK/labels_in`.
- `render`: write generated navigator nodes and the root skill.
- `relates`: inject cross-branch links based on centroid similarity.
- `walk`: print the generated navigation tree.
- `find`: print navigation paths matching a term.
- `stats`: report tree counts and unreached leaves.

## Development

Run the regression tests with the standard library test runner:

```bash
python3 -m unittest discover -s tests
python3 -m py_compile scripts/skillnav.py tests/test_skillnav.py
```

## License

MIT
