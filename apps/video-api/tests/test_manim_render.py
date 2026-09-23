from __future__ import annotations

import json
import sys
import time
import wave
from pathlib import Path

import pytest

from video_api.pipeline.manim_render import (
    SpeculativeRenderer,
    failed_scene_keys,
    main,
    reads_other_scene_data,
    render,
    resolve_jobs,
    scene_cache_keys,
    wav_is_complete,
)

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

FAKE_MANIM = '''import os
import sys
import time
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
with open(os.environ.get("CALLS_FILE", "calls.txt"), "a", encoding="utf-8") as calls:
    calls.write(key + "\\n")
time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
if key.startswith("Boom"):
    print("Traceback: kaboom")
    sys.exit(3)
out = media_dir / "videos" / Path(module).stem / quality / (key + ".mp4")
out.parent.mkdir(parents=True, exist_ok=True)
durations = Path("audio/en/durations.json")
out.write_text(key + open(module).read() + (durations.read_text() if durations.exists() else ""), encoding="utf-8")
'''


def _keys(
    module: str = MODULE,
    durations: dict | None = None,
    quality: str = "qh",
    style: str = "STYLE",
    texts: dict | None = None,
) -> dict[str, str]:
    return scene_cache_keys(
        module,
        style,
        ["SceneAEN", "SceneBEN"],
        durations or {"SceneAEN": 10, "SceneBEN": 12},
        texts or {},
        quality,
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

    # The style module holds every colour/geometry helper the scenes import, and
    # the narration text is an input too: losing either entry would keep serving
    # renders from before the edit, with the module and the durations unchanged.
    restyled = _keys(style="STYLE2")
    assert all(restyled[key] != base[key] for key in base)

    reworded = _keys(texts={"SceneAEN": "other words"})
    assert reworded["SceneAEN"] != base["SceneAEN"]
    assert reworded["SceneBEN"] == base["SceneBEN"]

    assert _keys(quality="ql")["SceneAEN"] != base["SceneAEN"]
    at_30 = scene_cache_keys(MODULE, "STYLE", ["SceneAEN"], {"SceneAEN": 10, "SceneBEN": 12}, {}, "qh", "30")
    assert at_30["SceneAEN"] != base["SceneAEN"]


def test_resolve_jobs() -> None:
    assert resolve_jobs("3", 8) == 3
    assert resolve_jobs("12", 4) == 4
    assert 1 <= resolve_jobs("auto", 8) <= 6
    assert resolve_jobs("", 1) == 1


def test_resolve_jobs_never_raises_on_a_typo() -> None:
    """A malformed MANIM_RENDER_JOBS must degrade to auto, not fail every render
    (and, in the worker, not escape into the repair loop)."""
    for bad in ("4cpu", "-2", "auto ", "  ", None, "NaN"):
        assert 1 <= resolve_jobs(bad, 8) <= 8


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


BOOMING_MODULE = MODULE + (
    "\nclass BoomAEN(Base):\n    def construct(self):\n        pass\n"
    "\nclass BoomBEN(Base):\n    def construct(self):\n        pass\n"
)


def test_render_names_every_failed_scene(tmp_path: Path) -> None:
    """One process per scene means several can fail at once (missing TeX package,
    full disk, a shared helper). The worker narrows its repair from the scene
    names in the log tail, so all of them have to be in the message — otherwise
    each extra broken scene costs its own repair attempt."""
    root, command = _workspace(tmp_path, BOOMING_MODULE)
    with pytest.raises(RuntimeError) as excinfo:
        render(
            root,
            "demo_en.py",
            ["SceneAEN", "BoomAEN", "BoomBEN"],
            "qh",
            2,
            root / "concat_en.txt",
            command=command,
        )
    assert failed_scene_keys(str(excinfo.value)) == {"BoomAEN", "BoomBEN"}


def test_render_sweeps_unpublished_partials(tmp_path: Path) -> None:
    """A crash between the copy and os.replace leaves a .mp4.part that no render
    reads and that nothing else would remove: the cache lives in the job dir and
    materialize keeps it across attempts."""
    root, command = _workspace(tmp_path)
    cache = root / "render_cache" / "qh"
    cache.mkdir(parents=True)
    (cache / "SceneAEN-deadbeef.mp4.part").write_text("half a copy", encoding="utf-8")

    render(root, "demo_en.py", ["SceneAEN"], "qh", 1, root / "concat_en.txt", command=command)

    assert list(cache.glob("*.mp4.part")) == []
    assert len(list(cache.glob("SceneAEN-*.mp4"))) == 1


def test_reads_other_scene_data() -> None:
    """A scene may only depend on its own duration and narration: those are the
    values the cache key covers for it."""
    assert not reads_other_scene_data("self.wait(duration(self.scene_key, 12))")
    assert reads_other_scene_data("self.wait(DURATIONS['SceneBEN'])")
    assert reads_other_scene_data("text = SEGMENT_TEXT.get('SceneBEN')")
    assert reads_other_scene_data('self.wait(duration("SceneBEN", 12))')


def _write_wav(path: Path, seconds: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(b"\x00\x00" * int(24000 * seconds))


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def test_wav_is_complete(tmp_path: Path) -> None:
    wav = tmp_path / "a.wav"
    _write_wav(wav, 0.5)
    assert wav_is_complete(wav, min_age_seconds=0)
    assert not wav_is_complete(wav, min_age_seconds=60)
    data = wav.read_bytes()
    truncated = tmp_path / "b.wav"
    truncated.write_bytes(data[: len(data) // 2])
    assert not wav_is_complete(truncated, min_age_seconds=0)
    assert not wav_is_complete(tmp_path / "missing.wav", min_age_seconds=0)


def _speculative(root: Path, command: list[str], scenes: list[str], jobs: int = 2) -> SpeculativeRenderer:
    return SpeculativeRenderer(
        root, "demo_en.py", scenes, "qh", "30", jobs, 0.45,
        command=command, probe=_wav_seconds, poll_seconds=0.05, min_wav_age_seconds=0,
    )


def _wait_for(predicate, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.05)


def test_speculative_render_feeds_the_final_pass(tmp_path: Path, monkeypatch) -> None:
    root, command = _workspace(tmp_path)
    (root / "audio" / "en" / "durations.json").unlink()
    monkeypatch.setenv("CALLS_FILE", str(root / "calls.txt"))
    scenes = ["SceneAEN", "SceneBEN"]
    spec = _speculative(root, command, scenes).start()
    _write_wav(root / "audio" / "en" / "SceneAEN.wav", 1.0)
    _write_wav(root / "audio" / "en" / "SceneBEN.wav", 2.0)
    _wait_for(lambda: len(spec.rendered_seconds) == 2)
    stats = spec.stop()
    assert sorted(stats["rendered_seconds"]) == scenes and stats["failed"] == {}
    assert not (root / "render_spec").exists()
    assert "SceneAEN" in (root / "render_logs" / "SceneAEN.speculative.log").name

    # The voice script's durations: SceneAEN matches the speculation exactly,
    # SceneBEN does not (e.g. a different tail padding) and renders again.
    (root / "audio" / "en" / "durations.json").write_text(json.dumps({"SceneAEN": 1.45, "SceneBEN": 9.0}))
    (root / "calls.txt").unlink()
    final = render(root, "demo_en.py", scenes, "qh", 2, root / "concat_en.txt", command=command, fps="30")
    assert final["cached"] == ["SceneAEN"]
    assert _calls(root) == ["SceneBEN"]
    reused = (root / "render_cache" / "qh-30fps").glob("SceneAEN-*.mp4")
    assert '"SceneAEN": 1.45' in next(reused).read_text()


def test_speculative_abort_kills_running_renders(tmp_path: Path, monkeypatch) -> None:
    root, command = _workspace(tmp_path)
    monkeypatch.setenv("CALLS_FILE", str(root / "calls.txt"))
    monkeypatch.setenv("FAKE_SLEEP", "30")
    spec = _speculative(root, command, ["SceneAEN"], jobs=1).start()
    _write_wav(root / "audio" / "en" / "SceneAEN.wav", 1.0)
    _wait_for(lambda: (root / "calls.txt").exists())
    started = time.monotonic()
    stats = spec.stop(abort=True)
    assert time.monotonic() - started < 10
    assert stats["rendered_seconds"] == {} and stats["failed"] == {}
    assert not list((root / "render_cache" / "qh-30fps").glob("*.mp4"))


def test_speculative_skips_a_scene_that_reads_another_scene_data(
    tmp_path: Path, monkeypatch
) -> None:
    """Such a scene would render differently in the shadow (which holds one
    duration) while producing the same digest, so the cache entry would be wrong.
    The regular pass renders it instead."""
    module = MODULE.replace("self.a = 1", 'self.a = duration("SceneBEN", 1)')
    root, command = _workspace(tmp_path, module)
    monkeypatch.setenv("CALLS_FILE", str(root / "calls.txt"))
    spec = _speculative(root, command, ["SceneAEN", "SceneBEN"]).start()
    _write_wav(root / "audio" / "en" / "SceneAEN.wav", 1.0)
    _write_wav(root / "audio" / "en" / "SceneBEN.wav", 2.0)
    _wait_for(lambda: spec.skipped and len(spec.rendered_seconds) == 1)
    stats = spec.stop()

    assert list(stats["skipped"]) == ["SceneAEN"]
    assert list(stats["rendered_seconds"]) == ["SceneBEN"]
    assert stats["failed"] == {}


def test_main_repeats_every_failed_scene_on_the_last_lines(tmp_path: Path, monkeypatch, capsys) -> None:
    """The worker only keeps the tail of the log, so the scene names have to be the
    last thing printed for the repair loop to narrow its invalidation."""
    root, command = _workspace(tmp_path, BOOMING_MODULE)
    monkeypatch.chdir(root)
    monkeypatch.setattr("video_api.pipeline.manim_render._manim_command", lambda: command)

    code = main(["--module", "demo_en.py", "--quality", "qh", "--jobs", "2", "SceneAEN", "BoomAEN", "BoomBEN"])

    assert code == 1
    stderr_lines = capsys.readouterr().err.strip().splitlines()
    assert stderr_lines[-2:] == ["render.failed scene=BoomAEN", "render.failed scene=BoomBEN"]
