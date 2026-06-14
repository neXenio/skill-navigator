import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "skillnav.py"


spec = importlib.util.spec_from_file_location("skillnav", SCRIPT)
skillnav = importlib.util.module_from_spec(spec)
spec.loader.exec_module(skillnav)


@contextmanager
def cwd(path):
    previous = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def write_skill(path, name, description, manifest=None):
    path.mkdir()
    (path / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: >\n  {description}\nmetadata:\n  category: test\n---\n",
        encoding="utf-8",
    )
    if manifest is not None:
        (path / "_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


class SkillnavTest(unittest.TestCase):
    def test_desc_of_reads_block_frontmatter_description(self):
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            write_skill(tmp_path / "alpha-skill", "alpha-skill", "Route alpha work")

            self.assertEqual(skillnav.desc_of(str(tmp_path / "alpha-skill")), "Route alpha work")

    def test_find_leaves_respects_include_exclude_and_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            write_skill(tmp_path / "alpha-one", "alpha-one", "Alpha one")
            write_skill(tmp_path / "alpha-two", "alpha-two", "Alpha two")
            write_skill(tmp_path / "beta-one", "beta-one", "Beta one")
            write_skill(tmp_path / "nav-node", "nav-node", "Navigator", {"navigator": True})

            with cwd(tmp_path):
                self.assertEqual(skillnav.find_leaves(["alpha-*"], ["*-two"]), ["alpha-one"])

    def test_find_leaves_tree_mode_takes_each_skill_tree_as_one_leaf(self):
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            plugin = tmp_path / "arbeitsrecht"
            (plugin / "skills" / "kuendigung").mkdir(parents=True)
            (plugin / "skills" / "kuendigung" / "SKILL.md").write_text(
                "---\nname: k\ndescription: >\n  Kuendigung\n---\n", encoding="utf-8")
            write_skill(tmp_path / "flat-skill", "flat-skill", "A flat one")

            with cwd(tmp_path):
                self.assertEqual(skillnav.find_leaves([], [], "top"), ["flat-skill"])
                self.assertEqual(
                    sorted(skillnav.find_leaves([], [], "tree")),
                    ["arbeitsrecht", "flat-skill"])

    def test_find_leaves_flat_mode_returns_nested_relpaths(self):
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            nested = tmp_path / "arbeitsrecht" / "skills" / "kuendigung"
            nested.mkdir(parents=True)
            (nested / "SKILL.md").write_text(
                "---\nname: k\ndescription: >\n  Kuendigung\n---\n", encoding="utf-8")

            with cwd(tmp_path):
                self.assertEqual(
                    skillnav.find_leaves([], [], "flat"),
                    [os.path.join("arbeitsrecht", "skills", "kuendigung")])

    def test_desc_of_falls_back_to_nested_skill_when_dir_has_none(self):
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            nested = tmp_path / "plugin" / "skills" / "inner"
            nested.mkdir(parents=True)
            (nested / "SKILL.md").write_text(
                "---\nname: inner\ndescription: >\n  Inner desc\n---\n", encoding="utf-8")

            self.assertEqual(skillnav.desc_of(str(tmp_path / "plugin")), "Inner desc")

    def test_render_apply_replaces_navigator_nodes_and_keeps_external_routers(self):
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            skills_dir = tmp_path / "skills"
            work = tmp_path / "work"
            labels = work / "labels_out"
            skills_dir.mkdir()
            labels.mkdir(parents=True)

            write_skill(skills_dir / "leaf-a", "leaf-a", "Leaf A")
            write_skill(skills_dir / "leaf-b", "leaf-b", "Leaf B")
            write_skill(skills_dir / "old-nav", "old-nav", "Old nav", {"navigator": True})
            write_skill(
                skills_dir / "external-router", "external-router", "Keep me", {"navigator": False}
            )

            tree = {
                "root_children": ["s1"],
                "nodes": {
                    "s1": {
                        "id": "s1",
                        "level": "station",
                        "parent": "ROOT",
                        "n": 2,
                        "terms": ["alpha", "beta"],
                        "samples": [],
                        "children": [],
                        "leaves": ["leaf-a", "leaf-b"],
                    }
                },
            }
            (work / "tree.json").write_text(json.dumps(tree), encoding="utf-8")
            (labels / "batch_00.json").write_text(
                json.dumps({"s1": "Station Alpha"}), encoding="utf-8"
            )

            args = SimpleNamespace(
                skills_dir=str(skills_dir),
                work=str(work),
                root="navigator",
                title="",
                lang="en",
                apply=True,
                layout="flat",
            )

            with cwd(ROOT), redirect_stdout(io.StringIO()):
                skillnav.cmd_render(args)

            self.assertFalse((skills_dir / "old-nav").exists())
            self.assertTrue((skills_dir / "external-router").exists())
            root_manifest = json.loads(
                (skills_dir / "navigator" / "_manifest.json").read_text(encoding="utf-8")
            )
            self.assertTrue(root_manifest["root"])
            station_manifest = json.loads(
                (skills_dir / "stn-station-alpha" / "_manifest.json").read_text(encoding="utf-8")
            )
            self.assertTrue(station_manifest["navigator"])
            station_skill = (skills_dir / "stn-station-alpha" / "SKILL.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("user-invokable: false", station_skill)

    def test_render_nested_layout_writes_nested_dirs_with_relative_links(self):
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            skills_dir = tmp_path / "skills"
            work = tmp_path / "work"
            labels = work / "labels_out"
            skills_dir.mkdir()
            labels.mkdir(parents=True)
            write_skill(skills_dir / "leaf-a", "leaf-a", "Leaf A")
            write_skill(skills_dir / "leaf-b", "leaf-b", "Leaf B")

            tree = {"root_children": ["s1"], "nodes": {"s1": {
                "id": "s1", "level": "station", "parent": "ROOT", "n": 2,
                "terms": ["alpha"], "samples": [], "children": [],
                "leaves": ["leaf-a", "leaf-b"]}}}
            (work / "tree.json").write_text(json.dumps(tree), encoding="utf-8")
            (labels / "batch_00.json").write_text(json.dumps({"s1": "Station Alpha"}), encoding="utf-8")

            args = SimpleNamespace(skills_dir=str(skills_dir), work=str(work),
                                   root="navigator", title="", lang="en", apply=True,
                                   layout="nested")
            with cwd(ROOT), redirect_stdout(io.StringIO()):
                skillnav.cmd_render(args)

            # node nested under the root dir, not a top-level sibling
            station = skills_dir / "navigator" / "stn-station-alpha"
            self.assertTrue((station / "SKILL.md").exists())
            self.assertFalse((skills_dir / "stn-station-alpha").exists())
            body = (station / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("`../../leaf-a/SKILL.md`", body)   # leaf link climbs out of nav tree
            self.assertIn("`../SKILL.md`", body)             # "Up one level" backlink to root
            # manifest folder_name carries the full relative leaf path
            man = json.loads((station / "_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(man["layout"], "nested")
            self.assertEqual(man["skills"][0]["folder_name"], "leaf-a")


if __name__ == "__main__":
    unittest.main()
