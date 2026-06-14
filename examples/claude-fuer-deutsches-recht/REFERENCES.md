# Leaf references (not copies)

This example references upstream skills by URL; it does **not** vendor them.
Source: [Klotzkette/claude-fuer-deutsches-recht](https://github.com/Klotzkette/claude-fuer-deutsches-recht/tree/main).

## How the reference works

In a normal local run, a navigator leaf-holder links each leaf as a relative
`SKILL.md` path (flat: `../<leaf>/SKILL.md`; nested: `../../<leaf>/SKILL.md`).
The export step in [`build.sh`](./build.sh) resolves each link: internal
navigator links stay relative, and any link that resolves to a leaf **outside**
the navigator tree is rewritten to its upstream URL:

```
https://github.com/Klotzkette/claude-fuer-deutsches-recht/tree/main/<leaf-path>
```

So the committed [`navigator-generated/`](./navigator-generated) tree contains
only generated `SKILL.md` + `_manifest.json` nodes, **no upstream files**, and
every leaf branch is an upstream URL.

## Discover modes → what a leaf path looks like

| `--discover` | a leaf is… | upstream `<leaf-path>` |
|--------------|------------|------------------------|
| `tree` (used here) | one whole plugin | `arbeitsrecht` |
| `flat` | one nested skill | `arbeitsrecht/skills/kuendigungsschutzklage-frist` |

To confirm nothing was copied:

```bash
find navigator-generated -type f ! -name SKILL.md ! -name _manifest.json   # → empty
grep -rl "github.com/Klotzkette" navigator-generated | head               # leaf URLs
```
