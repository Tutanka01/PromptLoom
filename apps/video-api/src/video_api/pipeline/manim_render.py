"""Parallel, cached per-scene Manim render.

Copied verbatim into each Manim video directory as ``render_scenes.py`` and run
by ``render_en.sh``, so it must stay standard-library only. One Manim process
per scene (each with its own media dir, so Tex caches never race), at most
``--jobs`` at a time. A rendered scene is kept in ``render_cache/`` under a key
covering everything its pixels depend on; a repair attempt that leaves a scene
unchanged reuses the MP4 instead of rendering it again. The worker also imports
``SpeculativeRenderer`` to fill that cache while the voice is being generated.
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
from typing import Callable

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


def cache_dir_for(root: Path, quality: str, fps: str) -> Path:
    return root / "render_cache" / (f"{quality}-{fps}fps" if fps else quality)


def _read_inputs(root: Path, module: str) -> tuple[str, str, dict]:
    style_path = root / module.replace("_en.py", "_style.py")
    segments = _load_json(root / "segments_en.json", {"segments": []})
    return (
        (root / module).read_text(encoding="utf-8"),
        style_path.read_text(encoding="utf-8") if style_path.exists() else "",
        {segment["key"]: segment["text"] for segment in segments["segments"]},
    )


def _render_scene(
    cwd: Path,
    module: str,
    key: str,
    quality: str,
    fps: str,
    manim: list[str],
    log_path: Path,
    dest: Path,
    track: Callable[[subprocess.Popen | None], None] | None = None,
) -> None:
    """Render one scene with its own media dir and publish it atomically to dest."""
    media_dir = Path("media") / "scenes" / key
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [*manim, f"-{quality}", *(["--fps", fps] if fps else []), "--media_dir", str(media_dir), module, key],
            cwd=cwd,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if track is not None:
            track(proc)
        try:
            returncode = proc.wait()
        finally:
            if track is not None:
                track(None)
    if returncode != 0:
        raise RuntimeError(
            f"manim failed for {key} (rc={returncode}), full log: {log_path}\n{_log_tail(log_path)}"
        )
    # The quality folder name depends on resolution and fps (e.g. 1080p30);
    # the per-scene media dir holds exactly one final MP4, so look it up.
    outputs = sorted((cwd / media_dir / "videos" / Path(module).stem).glob(f"*/{key}.mp4"))
    if len(outputs) != 1:
        raise RuntimeError(f"manim produced {len(outputs)} videos for {key} under {media_dir}, full log: {log_path}")
    partial = dest.with_suffix(".mp4.part")
    shutil.copyfile(outputs[0], partial)
    os.replace(partial, dest)


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
    module_source, style_source, segment_text = _read_inputs(root, module)
    keys = scene_cache_keys(
        module_source,
        style_source,
        scene_keys,
        _load_json(root / "audio" / "en" / "durations.json", {}),
        segment_text,
        quality,
        fps,
    )
    cache_dir = cache_dir_for(root, quality, fps)
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
        _render_scene(root, module, key, quality, fps, manim, log_dir / f"{key}.log", cached_path[key])
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


def wav_is_complete(path: Path, min_age_seconds: float = 1.0) -> bool:
    """True once a WAV is fully written: RIFF size matches the file (writers
    patch it on close) and the file has not been touched for a moment."""
    try:
        stat = path.stat()
        if stat.st_size <= 44 or time.time() - stat.st_mtime < min_age_seconds:
            return False
        with path.open("rb") as handle:
            header = handle.read(12)
    except OSError:
        return False
    if header[:4] != b"RIFF" or header[8:12] != b"WAVE":
        return False
    return int.from_bytes(header[4:8], "little") + 8 == stat.st_size


def ffprobe_duration(path: Path) -> float:
    # Same command as generate_voice_en.py, so the float matches durations.json.
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(path)],
        check=True,
        text=True,
        capture_output=True,
    )
    return float(result.stdout.strip())


class SpeculativeRenderer:
    """Render Manim scenes while the voice is still being generated.

    As soon as a scene's WAV is complete, its duration is computed with the
    voice script's own formula and the scene is rendered in a scratch copy of
    the video dir holding just that duration; the MP4 lands in render_cache/.
    The regular render that follows the voice step uses the authoritative
    durations.json: a scene rendered with the right duration is a cache hit,
    any mismatch simply renders again. Speculation can waste CPU, never
    desynchronise voice and picture.
    """

    def __init__(
        self,
        root: Path,
        module: str,
        scene_keys: list[str],
        quality: str,
        fps: str,
        jobs: int,
        tail_padding: float,
        command: list[str] | None = None,
        probe: Callable[[Path], float] = ffprobe_duration,
        poll_seconds: float = 1.0,
        min_wav_age_seconds: float = 1.0,
    ) -> None:
        self.root = root
        self.module = module
        self.scene_keys = list(scene_keys)
        self.quality = quality
        self.fps = fps
        self.tail_padding = tail_padding
        self.manim = command or _manim_command()
        self.probe = probe
        self.poll_seconds = poll_seconds
        self.min_wav_age_seconds = min_wav_age_seconds
        self.cache_dir = cache_dir_for(root, quality, fps)
        self.spec_dir = root / "render_spec"
        self.log_dir = root / "render_logs"
        self._pool = ThreadPoolExecutor(max_workers=max(1, jobs))
        self._stop = threading.Event()
        self._aborted = False
        self._lock = threading.Lock()
        self._procs: dict[str, subprocess.Popen] = {}
        self._thread = threading.Thread(target=self._watch, name="manim-speculative", daemon=True)
        self.rendered_seconds: dict[str, float] = {}
        self.already_cached: list[str] = []
        self.failed: dict[str, str] = {}

    def start(self) -> "SpeculativeRenderer":
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._thread.start()
        return self

    def stop(self, abort: bool = False) -> dict:
        """Stop watching; queued renders are dropped (the regular render does
        them with full parallelism). Running renders finish, or are killed
        when aborting (the voice failed)."""
        with self._lock:
            self._aborted = abort
        self._stop.set()
        self._thread.join()
        if abort:
            with self._lock:
                for proc in self._procs.values():
                    proc.kill()
        self._pool.shutdown(wait=True, cancel_futures=True)
        shutil.rmtree(self.spec_dir, ignore_errors=True)
        return {
            "rendered_seconds": dict(self.rendered_seconds),
            "already_cached": list(self.already_cached),
            "failed": dict(self.failed),
        }

    def _watch(self) -> None:
        try:
            module_source, style_source, segment_text = _read_inputs(self.root, self.module)
        except Exception as exc:
            self.failed["*"] = f"cannot read sources: {exc}"
            return
        pending = list(self.scene_keys)
        while pending and not self._stop.is_set():
            for key in list(pending):
                wav = self.root / "audio" / "en" / f"{key}.wav"
                if not wav_is_complete(wav, self.min_wav_age_seconds):
                    continue
                pending.remove(key)
                try:
                    duration = round(self.probe(wav) + self.tail_padding, 3)
                except Exception as exc:
                    self.failed[key] = f"duration probe failed: {exc}"
                    continue
                digest = scene_cache_keys(
                    module_source, style_source, self.scene_keys, {key: duration}, segment_text, self.quality, self.fps
                )[key]
                dest = self.cache_dir / f"{key}-{digest}.mp4"
                if dest.exists():
                    self.already_cached.append(key)
                    continue
                self._pool.submit(self._render, key, duration, dest, module_source, style_source)
            self._stop.wait(self.poll_seconds)

    def _track(self, key: str) -> Callable[[subprocess.Popen | None], None]:
        def track(proc: subprocess.Popen | None) -> None:
            with self._lock:
                if proc is None:
                    self._procs.pop(key, None)
                    return
                self._procs[key] = proc
                if self._aborted:
                    proc.kill()

        return track

    def _render(self, key: str, duration: float, dest: Path, module_source: str, style_source: str) -> None:
        shadow = self.spec_dir / key
        started = time.monotonic()
        try:
            shutil.rmtree(shadow, ignore_errors=True)
            (shadow / "audio" / "en").mkdir(parents=True)
            (shadow / self.module).write_text(module_source, encoding="utf-8")
            (shadow / self.module.replace("_en.py", "_style.py")).write_text(style_source, encoding="utf-8")
            shutil.copyfile(self.root / "segments_en.json", shadow / "segments_en.json")
            (shadow / "audio" / "en" / "durations.json").write_text(json.dumps({key: duration}), encoding="utf-8")
            _render_scene(
                shadow,
                self.module,
                key,
                self.quality,
                self.fps,
                self.manim,
                self.log_dir / f"{key}.speculative.log",
                dest,
                track=self._track(key),
            )
            self.rendered_seconds[key] = round(time.monotonic() - started, 2)
        except Exception as exc:
            if not self._aborted:
                self.failed[key] = str(exc).splitlines()[0]
        finally:
            shutil.rmtree(shadow, ignore_errors=True)


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
