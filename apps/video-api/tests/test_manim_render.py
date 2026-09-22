from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from video_api.pipeline.manim_render import render, resolve_jobs, scene_cache_keys

MODULE = '''from manim import *

def helper():
    return 1

class Base(Scene):
    pass

class SceneAEN(Base):
    def construct(self):
        self.a = 1

class SceneBEN(Base):
    def construct(self):
        self.b = 2
'''

FAKE_MANIM = '''import sys
from pathlib import Path

args = sys.argv[1:]
height, fps = {"-qh": ("1080", "60"), "-ql": ("480", "15")}[args.pop(0)]
if args[0] == "--fps":
    fps = args[1]
    args = args[2:]
assert args[0] == "--media_dir"
media_dir = Path(args[1])
module, key = args[2], args[3]
quality = height + "p" + fps
with open("calls.txt", "a", encoding="utf-8") as calls:
    calls.write(key + "\\n")
if key.startswith("Boom"):
    print("Traceback: kaboom")
    sys.exit(3)
out = media_dir / "videos" / Path(module).stem / quality / (key + ".mp4")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(key + open(module).read(), encoding="utf-8")
'''


def _keys(module: str = MODULE, durations: dict | None = None, quality: str = "qh") -> dict[str, str]:
    return scene_cache_keys(
        module, "STYLE", ["SceneAEN", "SceneBEN"], durations or {"SceneAEN": 10, "SceneBEN": 12}, {}, quality
    )


def test_cache_key_tracks_only_what_a_scene_depends_on() -> None:
    base = _keys()
    edited_b = _keys(MODULE.replace("self.b = 2", "self.b = 3"))
    assert edited_b["SceneAEN"] == base["SceneAEN"]
    assert edited_b["SceneBEN"] != base["SceneBEN"]

    edited_helper = _keys(MODULE.replace("return 1", "return 2"))
    assert all(edited_helper[key] != base[key] for key in base)

    longer_a = _keys(durations={"SceneAEN": 11, "SceneBEN": 12})
    assert longer_a["SceneAEN"] != base["SceneAEN"]
    assert longer_a["SceneBEN"] == base["SceneBEN"]

    assert _keys(quality="ql")["SceneAEN"] != base["SceneAEN"]
    at_30 = scene_cache_keys(MODULE, "STYLE", ["SceneAEN"], {"SceneAEN": 10, "SceneBEN": 12}, {}, "qh", "30")
    assert at_30["SceneAEN"] != base["SceneAEN"]


def test_resolve_jobs() -> None:
    assert resolve_jobs("3", 8) == 3
    assert resolve_jobs("12", 4) == 4
    assert 1 <= resolve_jobs("auto", 8) <= 6
    assert resolve_jobs("", 1) == 1


def _workspace(tmp_path: Path, module: str = MODULE) -> tuple[Path, list[str]]:
    (tmp_path / "demo_en.py").write_text(module, encoding="utf-8")
    (tmp_path / "demo_style.py").write_text("STYLE", encoding="utf-8")
    (tmp_path / "segments_en.json").write_text(
        json.dumps({"segments": [{"key": "SceneAEN", "text": "a"}, {"key": "SceneBEN", "text": "b"}]}),
        encoding="utf-8",
    )
    (tmp_path / "audio" / "en").mkdir(parents=True)
    (tmp_path / "audio" / "en" / "durations.json").write_text(
        json.dumps({"SceneAEN": 10, "SceneBEN": 12}), encoding="utf-8"
    )
    fake = tmp_path / "fake_manim.py"
    fake.write_text(FAKE_MANIM, encoding="utf-8")
    return tmp_path, [sys.executable, str(fake)]


def _calls(root: Path) -> list[str]:
    path = root / "calls.txt"
    return sorted(path.read_text(encoding="utf-8").split()) if path.exists() else []


def test_render_parallel_then_reuses_unchanged_scenes(tmp_path: Path, capsys) -> None:
    root, command = _workspace(tmp_path)
    scenes = ["SceneAEN", "SceneBEN"]
    concat = root / "concat_en.txt"

    stats = render(root, "demo_en.py", scenes, "qh", 2, concat, command=command)
    assert _calls(root) == scenes
    assert sorted(stats["rendered_seconds"]) == scenes and stats["cached"] == []
    listed = [line.split("'")[1] for line in concat.read_text(encoding="utf-8").splitlines()]
    assert [Path(p).name.split("-")[0] for p in listed] == scenes
    assert all((root / p).exists() for p in listed)
    assert json.loads((root / "render_stats.json").read_text())["jobs"] == 2
    out = capsys.readouterr().out
    assert "Rendered SceneAEN (" in out and "Rendered SceneBEN (" in out

    # A repair rewrites SceneBEN only: SceneAEN comes from the cache and the
    # superseded SceneBEN entry is pruned.
    (root / "calls.txt").unlink()
    (root / "demo_en.py").write_text(MODULE.replace("self.b = 2", "self.b = 5"), encoding="utf-8")
    stats = render(root, "demo_en.py", scenes, "qh", 2, concat, command=command)
    assert _calls(root) == ["SceneBEN"]
    assert stats["cached"] == ["SceneAEN"]
    assert "Rendered SceneAEN (cache)" in capsys.readouterr().out
    assert len(list((root / "render_cache" / "qh").glob("*.mp4"))) == 2


def test_render_fps_override(tmp_path: Path) -> None:
    root, command = _workspace(tmp_path)
    stats = render(root, "demo_en.py", ["SceneAEN"], "qh", 1, root / "concat_en.txt", command=command, fps="30")
    assert stats["fps"] == "30"
    assert (root / "media" / "scenes" / "SceneAEN" / "videos" / "demo_en" / "1080p30" / "SceneAEN.mp4").exists()
    assert len(list((root / "render_cache" / "qh-30fps").glob("SceneAEN-*.mp4"))) == 1


def test_render_failure_surfaces_scene_log(tmp_path: Path) -> None:
    module = MODULE + "\nclass BoomEN(Base):\n    def construct(self):\n        pass\n"
    root, command = _workspace(tmp_path, module)
    with pytest.raises(RuntimeError, match=r"manim failed for BoomEN \(rc=3\).*render_logs/BoomEN.log"):
        render(root, "demo_en.py", ["BoomEN"], "qh", 1, root / "concat_en.txt", command=command)
    assert "kaboom" in (root / "render_logs" / "BoomEN.log").read_text(encoding="utf-8")
    assert not (root / "concat_en.txt").exists()
