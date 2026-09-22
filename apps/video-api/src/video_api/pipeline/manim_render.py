"""Parallel, cached per-scene Manim render.

Copied verbatim into each Manim video directory as ``render_scenes.py`` and run
by ``render_en.sh``, so it must stay standard-library only. One Manim process
per scene (each with its own media dir, so Tex caches never race), at most
``--jobs`` at a time. A rendered scene is kept in ``render_cache/`` under a key
covering everything its pixels depend on; a repair attempt that leaves a scene
unchanged reuses the MP4 instead of rendering it again.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from pathlib import Path

QUALITIES = ("ql", "qm", "qh", "qp", "qk")
CACHE_VERSION = "1"


def default_jobs(scene_count: int) -> int:
    try:
        cpus = len(os.sched_getaffinity(0))
    except AttributeError:
        cpus = os.cpu_count() or 1
    return max(1, min(scene_count, cpus // 2, 6))


def resolve_jobs(raw: str | None, scene_count: int) -> int:
    value = (raw or "").strip().lower()
    if value in {"", "0", "auto"}:
        return default_jobs(scene_count)
    return max(1, min(scene_count, int(value)))


def _shared_and_scene_sources(module_source: str, scene_keys: list[str]) -> tuple[str, dict[str, str]]:
    """Split the module into its shared part (imports, helpers, base class) and
    each scene class's own source. Helpers a custom scene defines at module
    level land in the shared part, so editing one invalidates every scene —
    conservative, never stale."""
    tree = ast.parse(module_source)
    wanted = set(scene_keys)
    shared: list[str] = []
    scenes: dict[str, str] = {}
    for node in tree.body:
        segment = ast.get_source_segment(module_source, node, padded=True) or ""
        if isinstance(node, ast.ClassDef) and node.name in wanted:
            decorators = "".join(
                (ast.get_source_segment(module_source, deco) or "") + "\n" for deco in node.decorator_list
            )
            scenes[node.name] = decorators + segment
        else:
            shared.append(segment)
    return "\n".join(shared), scenes


def scene_cache_keys(
    module_source: str,
    style_source: str,
    scene_keys: list[str],
    durations: dict,
    segment_text: dict,
    quality: str,
    fps: str = "",
) -> dict[str, str]:
    shared, scenes = _shared_and_scene_sources(module_source, scene_keys)
    keys: dict[str, str] = {}
    for key in scene_keys:
        payload = json.dumps(
            {
                "version": CACHE_VERSION,
                "quality": quality,
                "fps": fps,
                "shared": shared,
                "style": style_source,
                "scene": scenes.get(key, ""),
                "duration": durations.get(key),
                "text": segment_text.get(key),
            },
            sort_keys=True,
            ensure_ascii=True,
        )
        keys[key] = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return keys


def _manim_command() -> list[str]:
    if os.environ.get("MANIM_USE_UV", "1") == "1":
        return ["uv", "run", "--with", "manim", "python", "-m", "manim"]
    return [sys.executable, "-m", "manim"]


def _load_json(path: Path, fallback):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return fallback


def _log_tail(path: Path, lines: int = 40) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-lines:])


def render(
    root: Path,
    module: str,
    scene_keys: list[str],
    quality: str,
    jobs: int,
    concat_path: Path,
    command: list[str] | None = None,
    fps: str = "",
) -> dict:
    module_path = root / module
    style_path = root / module.replace("_en.py", "_style.py")
    segments = _load_json(root / "segments_en.json", {"segments": []})
    keys = scene_cache_keys(
        module_path.read_text(encoding="utf-8"),
        style_path.read_text(encoding="utf-8") if style_path.exists() else "",
        scene_keys,
        _load_json(root / "audio" / "en" / "durations.json", {}),
        {segment["key"]: segment["text"] for segment in segments["segments"]},
        quality,
        fps,
    )
    cache_dir = root / "render_cache" / (f"{quality}-{fps}fps" if fps else quality)
    log_dir = root / "render_logs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    cached_path = {key: cache_dir / f"{key}-{keys[key]}.mp4" for key in scene_keys}
    pending = [key for key in scene_keys if not cached_path[key].exists()]
    for key in scene_keys:
        if key not in pending:
            print(f"Rendered {key} (cache)", flush=True)

    manim = command or _manim_command()
    print_lock = threading.Lock()
    rendered: dict[str, float] = {}

    def _render_one(key: str) -> None:
        started = time.monotonic()
        media_dir = Path("media") / "scenes" / key
        log_path = log_dir / f"{key}.log"
        with log_path.open("w", encoding="utf-8") as log:
            proc = subprocess.run(
                [*manim, f"-{quality}", *(["--fps", fps] if fps else []), "--media_dir", str(media_dir), module, key],
                cwd=root,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
        if proc.returncode != 0:
            raise RuntimeError(
                f"manim failed for {key} (rc={proc.returncode}), full log: {log_path}\n{_log_tail(log_path)}"
            )
        # The quality folder name depends on resolution and fps (e.g. 1080p30);
        # the per-scene media dir holds exactly one final MP4, so look it up.
        outputs = sorted((root / media_dir / "videos" / Path(module).stem).glob(f"*/{key}.mp4"))
        if len(outputs) != 1:
            raise RuntimeError(f"manim produced {len(outputs)} videos for {key} under {media_dir}, full log: {log_path}")
        output = outputs[0]
        partial = cached_path[key].with_suffix(".mp4.part")
        shutil.copyfile(output, partial)
        os.replace(partial, cached_path[key])
        elapsed = time.monotonic() - started
        with print_lock:
            rendered[key] = round(elapsed, 2)
            print(f"Rendered {key} ({elapsed:.1f}s)", flush=True)

    started = time.monotonic()
    if pending:
        pool = ThreadPoolExecutor(max_workers=jobs)
        futures = [pool.submit(_render_one, key) for key in pending]
        wait(futures, return_when=FIRST_EXCEPTION)
        pool.shutdown(wait=True, cancel_futures=True)
        for future in futures:
            if future.done() and not future.cancelled() and future.exception() is not None:
                raise future.exception()

    concat_path.write_text(
        "".join(f"file '{cached_path[key].relative_to(root)}'\n" for key in scene_keys),
        encoding="utf-8",
    )
    keep = {path.name for path in cached_path.values()}
    for stale in cache_dir.glob("*.mp4"):
        if stale.name not in keep:
            stale.unlink()
    stats = {
        "jobs": jobs,
        "quality": quality,
        "fps": fps or None,
        "wall_seconds": round(time.monotonic() - started, 2),
        "rendered_seconds": rendered,
        "cached": [key for key in scene_keys if key not in pending],
    }
    (root / "render_stats.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    print(
        f"render.summary scenes={len(scene_keys)} rendered={len(pending)} "
        f"cached={len(scene_keys) - len(pending)} jobs={jobs} wall={stats['wall_seconds']}s",
        flush=True,
    )
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True)
    parser.add_argument("--quality", default="qm", choices=QUALITIES)
    parser.add_argument("--fps", default=os.environ.get("MANIM_FPS", ""), help="override the preset frame rate")
    parser.add_argument("--jobs", default=os.environ.get("MANIM_RENDER_JOBS", "auto"))
    parser.add_argument("--concat", default="concat_en.txt")
    parser.add_argument("scenes", nargs="+")
    args = parser.parse_args(argv)
    root = Path.cwd()
    try:
        render(
            root,
            args.module,
            args.scenes,
            args.quality,
            resolve_jobs(args.jobs, len(args.scenes)),
            root / args.concat,
            fps=args.fps.strip(),
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
