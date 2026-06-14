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


if __name__ == "__main__":
    unittest.main()
