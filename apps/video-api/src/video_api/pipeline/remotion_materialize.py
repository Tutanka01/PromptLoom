"""Materialize a Remotion `video_dir`: same downstream contract as Manim.

Produces a job-local working directory whose scripts the shared orchestrator
shells out to, exactly like the Manim path:

- ``segments_en.json``      -> consumed by the copied ``generate_voice_en.py``
                               (Chatterbox), which writes ``audio/en/durations.json``
                               + ``voiceover_en.mp3``.
- ``scenes_map.json``       -> ordered [{key, component, props}]; the render maps
                               each scene to a registered React component.
- ``build_video_json.py``   -> durations.json + scenes_map.json -> ``video.json``
                               (durationInFrames = round(seconds * 60)).
- ``render_en.sh``          -> builds video.json, injects this job's custom scenes
                               + a per-job entry into the *shared* Remotion project
                               (isolated by a unique id => concurrency-safe), runs
                               ``npx remotion render`` -> ``final/<slug>-en-silent.mp4``.
- ``remotion_scenes/*.tsx`` -> bespoke ``Custom`` scene components (written by the
                               Remotion scene-coder); ``jobScenes_index.ts`` re-exports
                               them as the ``COMPONENTS`` map.
- ``assemble_en.sh``        -> shared with Manim (mux silent video + voiceover).

Only ``render_en.sh`` differs from the Manim engine; voice/assemble/verify are
identical.
"""
from __future__ import annotations

import json
import logging
import shutil
import uuid
from pathlib import Path

from video_api.config import Settings
from video_api.pipeline.materialize import _assemble_script, slugify
from video_api.pipeline.voice import prune_stale_audio, voice_signature
from video_api.schemas import RemotionBlueprint, RemotionScene

logger = logging.getLogger(__name__)


def _segments_json(blueprint: RemotionBlueprint) -> dict:
    return {
        "segments": [
            {"key": scene.key, "title": scene.title, "text": scene.narration}
            for scene in blueprint.scenes
        ]
    }


def _scenes_map(blueprint: RemotionBlueprint, fps: int) -> dict:
    """Ordered scene->component map. Custom scenes are registered under their key."""
    scenes = []
    for scene in blueprint.scenes:
        component = scene.key if scene.is_custom else scene.component
        scenes.append(
            {
                "key": scene.key,
                "component": component,
                "custom": scene.is_custom,
                "transition": getattr(scene, "transition", "auto"),
                "props": dict(scene.props or {}),
            }
        )
    return {"fps": fps, "scenes": scenes}


def _script_markdown(blueprint: RemotionBlueprint) -> str:
    sections = [f"## {s.key}: {s.title} ({s.component})\n\n{s.narration}\n" for s in blueprint.scenes]
    return f"# {blueprint.title} Script\n\n" + "\n".join(sections)


_BUILD_VIDEO_JSON = '''#!/usr/bin/env python3
"""Build Remotion video.json from the TTS durations + the scene/component map.

durationInFrames per scene = round(audio_seconds * FPS), floored so a scene is
never shorter than MIN_FRAMES. The render is silent (embedAudio=false); the
global voiceover is muxed later by assemble_en.sh.
"""
import json
from pathlib import Path

FPS = __FPS__
MIN_FRAMES = FPS  # >= 1 second

ROOT = Path(__file__).resolve().parent
durations = json.loads((ROOT / "audio" / "en" / "durations.json").read_text(encoding="utf-8"))
scene_map = json.loads((ROOT / "scenes_map.json").read_text(encoding="utf-8"))

scenes = []
for entry in scene_map["scenes"]:
    key = entry["key"]
    seconds = float(durations.get(key, 6.0))
    frames = max(MIN_FRAMES, round(seconds * FPS))
    scenes.append({
        "component": entry["component"],
        "props": entry.get("props", {}),
        "transition": entry.get("transition", "auto"),
        "durationInFrames": frames,
    })

video = {"embedAudio": False, "scenes": scenes}
(ROOT / "video.json").write_text(json.dumps(video, indent=2) + "\\n", encoding="utf-8")
total = sum(s["durationInFrames"] for s in scenes)
print(f"video.json: {len(scenes)} scenes, {total} frames ({total / FPS:.1f}s)")
'''


def _build_video_json_py(fps: int) -> str:
    return _BUILD_VIDEO_JSON.replace("__FPS__", str(fps))


def _entry_tsx(entry_id: str, fps: int) -> str:
    """Per-job Remotion entry: registers the data-driven `Video` composition with
    a registry = palette components + this job's custom scenes."""
    return f'''import React from "react";
import {{ Composition, registerRoot }} from "remotion";
import {{ MainComposition, videoSchema }} from "../MainComposition";
import {{ SCENE_COMPONENTS }} from "../registry";
import {{ COMPONENTS as JOB_COMPONENTS }} from "../jobScenes/{entry_id}/index";

const REGISTRY = {{ ...SCENE_COMPONENTS, ...JOB_COMPONENTS }};
const JobMain: React.FC<any> = (props) => <MainComposition {{...props}} registry={{REGISTRY}} />;

const Root: React.FC = () => (
  <Composition
    id="Video"
    component={{JobMain}}
    schema={{videoSchema}}
    defaultProps={{{{ scenes: [], embedAudio: false }}}}
    fps={{{fps}}}
    width={{1920}}
    height={{1080}}
    durationInFrames={{{fps}}}
    calculateMetadata={{({{ props }}: any) => ({{
      durationInFrames: Math.max(
        1,
        props.scenes.reduce((s: number, sc: any) => s + sc.durationInFrames, 0)
      ),
    }})}}
  />
);

registerRoot(Root);
'''


def _render_script(
    blueprint: RemotionBlueprint,
    remotion_dir: Path,
    entry_id: str,
    fps: int,
    concurrency: str,
    x264_preset: str,
) -> str:
    silent = f"final/{blueprint.slug}-en-silent.mp4"
    # The per-job entry imports `../jobScenes/<entry_id>/index`; the heredoc below
    # writes that entry verbatim (it contains no shell metacharacters).
    entry_body = _entry_tsx(entry_id, fps)
    return f'''#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
VIDEO_DIR="$(pwd)"

QUALITY="${{QUALITY:-qm}}"
REMOTION_DIR="${{VIDEO_API_REMOTION_DIR:-{remotion_dir}}}"
ENTRY_ID="{entry_id}"

SCALE=1
CRF=18
if [[ "${{QUALITY}}" == "ql" ]]; then
  SCALE=0.5
  CRF=28
fi

# 1. durations.json (from TTS) + scenes_map.json -> video.json
python3 build_video_json.py

# 2. Inject this job's custom scenes + a per-job entry into the shared project.
#    Isolated by ENTRY_ID so concurrent jobs never collide; cleaned up on exit.
ENTRY_DIR="${{REMOTION_DIR}}/src/entries"
SCENES_DIR="${{REMOTION_DIR}}/src/jobScenes/${{ENTRY_ID}}"
mkdir -p "${{ENTRY_DIR}}" "${{SCENES_DIR}}"
cleanup() {{ rm -f "${{ENTRY_DIR}}/${{ENTRY_ID}}.tsx"; rm -rf "${{SCENES_DIR}}"; }}
trap cleanup EXIT

if compgen -G "remotion_scenes/*.tsx" > /dev/null; then
  cp -f remotion_scenes/*.tsx "${{SCENES_DIR}}/"
fi
cp -f jobScenes_index.ts "${{SCENES_DIR}}/index.ts"

cat > "${{ENTRY_DIR}}/${{ENTRY_ID}}.tsx" <<'REMOTION_ENTRY_EOF'
{entry_body}REMOTION_ENTRY_EOF

# 3. Render (silent). verify checks 1920x1080 + render_fps only on the final (scale=1) pass.
mkdir -p final
( cd "${{REMOTION_DIR}}" && npx --no-install remotion render \\
    "src/entries/${{ENTRY_ID}}.tsx" Video \\
    "${{VIDEO_DIR}}/{silent}" \\
    --props="${{VIDEO_DIR}}/video.json" \\
    --scale="${{SCALE}}" \\
    --crf="${{CRF}}" \\
    --concurrency="{concurrency}" \\
    --x264-preset="{x264_preset}" \\
    --log=error )

echo "Wrote {silent}"
'''


class RemotionMaterializer:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _remotion_dir(self) -> Path:
        return self.settings.repo_root / "apps" / "video-api" / "remotion"

    def materialize(self, blueprint: RemotionBlueprint, workspace: Path) -> Path:
        theme = slugify(blueprint.theme)
        docs_dir = workspace / "docs" / "videos" / theme / blueprint.slug
        video_dir = workspace / "videos" / theme / blueprint.slug
        entry_id = "job_" + uuid.uuid4().hex[:16]
        logger.info(
            "remotion.materialize.start title=%s theme=%s slug=%s scenes=%d entry_id=%s",
            blueprint.title,
            theme,
            blueprint.slug,
            len(blueprint.scenes),
            entry_id,
        )
        docs_dir.mkdir(parents=True, exist_ok=True)
        video_dir.mkdir(parents=True, exist_ok=True)
        for name in ["final", "renders"]:
            stale = video_dir / name
            if stale.exists():
                shutil.rmtree(stale)
        # audio/ is NOT wiped: per-segment WAVs are cached by text+voice-params hash
        # so a repair attempt only re-synthesizes the segments that actually changed.
        prune_stale_audio(
            video_dir,
            _segments_json(blueprint)["segments"],
            voice_signature(self.settings),
        )
        scenes_dir = video_dir / "remotion_scenes"
        if scenes_dir.exists():
            shutil.rmtree(scenes_dir)
        scenes_dir.mkdir(parents=True, exist_ok=True)

        (docs_dir / "script.md").write_text(_script_markdown(blueprint), encoding="utf-8")
        (video_dir / "segments_en.json").write_text(
            json.dumps(_segments_json(blueprint), indent=2) + "\n", encoding="utf-8"
        )
        fps = self.settings.render_fps
        (video_dir / "scenes_map.json").write_text(
            json.dumps(_scenes_map(blueprint, fps), indent=2) + "\n", encoding="utf-8"
        )
        (video_dir / "build_video_json.py").write_text(_build_video_json_py(fps), encoding="utf-8")
        # Default (palette-only) custom-scene index; the scene-coder overwrites it
        # together with remotion_scenes/*.tsx when there are Custom scenes.
        (video_dir / "jobScenes_index.ts").write_text(
            "export const COMPONENTS: Record<string, React.FC<any>> = {};\n", encoding="utf-8"
        )

        voice_src = (
            self.settings.repo_root
            / "videos"
            / "linux-fondamentaux"
            / "002-c-est-quoi-un-syscall"
            / "generate_voice_en.py"
        )
        if not voice_src.exists():
            raise FileNotFoundError(f"Missing reference voice generator: {voice_src}")
        shutil.copyfile(voice_src, video_dir / "generate_voice_en.py")

        render_path = video_dir / "render_en.sh"
        assemble_path = video_dir / "assemble_en.sh"
        render_path.write_text(
            _render_script(
                blueprint,
                self._remotion_dir(),
                entry_id,
                fps,
                self.settings.remotion_concurrency,
                self.settings.render_x264_preset,
            ),
            encoding="utf-8",
        )
        assemble_path.write_text(_assemble_script(blueprint), encoding="utf-8")
        render_path.chmod(0o755)
        assemble_path.chmod(0o755)
        logger.info(
            "remotion.materialize.done video_dir=%s render=%s assemble=%s custom_scenes=%d",
            video_dir,
            render_path,
            assemble_path,
            sum(1 for s in blueprint.scenes if s.is_custom),
        )
        return video_dir

    def write_scene_codes(
        self,
        video_dir: Path,
        blueprint: RemotionBlueprint,
        scene_codes: dict[str, str],
    ) -> None:
        """Write bespoke Custom scene TSX + the jobScenes index re-exporting them.

        Custom scenes without generated code fall back to a palette component in
        scenes_map.json (handled by the scene-coder), so the index only needs the
        scenes that actually produced code.
        """
        scenes_dir = video_dir / "remotion_scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)
        imports: list[str] = []
        entries: list[str] = []
        for key, code in scene_codes.items():
            (scenes_dir / f"{key}.tsx").write_text(code, encoding="utf-8")
            imports.append(f'import {{ {key} }} from "./{key}";')
            entries.append(f"  {key},")
        index = (
            'import React from "react";\n'
            + "\n".join(imports)
            + ("\n\n" if imports else "\n")
            + "export const COMPONENTS: Record<string, React.FC<any>> = {\n"
            + "\n".join(entries)
            + ("\n" if entries else "")
            + "};\n"
        )
        (video_dir / "jobScenes_index.ts").write_text(index, encoding="utf-8")
        logger.info("remotion.scene_codes_written video_dir=%s custom_scenes=%d", video_dir, len(scene_codes))


def fallback_custom_to_palette(video_dir: Path, blueprint: RemotionBlueprint, failed_keys: set[str]) -> None:
    """Rewrite scenes_map.json so Custom scenes in *failed_keys* render as a
    deterministic palette BulletScene built from their narration.

    Guarantees the render never references a Custom component that has no code,
    mirroring the Manim engine's deterministic-template fallback.
    """
    if not failed_keys:
        return
    from video_api.pipeline.remotion_blueprint import _bullets_from_narration

    by_key = {scene.key: scene for scene in blueprint.scenes}
    path = video_dir / "scenes_map.json"
    scene_map = json.loads(path.read_text(encoding="utf-8"))
    for entry in scene_map["scenes"]:
        if entry["key"] in failed_keys:
            scene = by_key[entry["key"]]
            entry["component"] = "BulletScene"
            entry["custom"] = False
            entry["props"] = {
                "title": scene.title,
                "bullets": _bullets_from_narration(scene.narration, 4),
            }
    path.write_text(json.dumps(scene_map, indent=2) + "\n", encoding="utf-8")
    logger.info("remotion.custom_fallback video_dir=%s fell_back=%d", video_dir, len(failed_keys))


def validate_remotion_video_source(video_dir: Path) -> None:
    """Cheap static checks before the expensive voice/render steps."""
    required = ["segments_en.json", "scenes_map.json", "build_video_json.py", "render_en.sh", "assemble_en.sh"]
    missing = [name for name in required if not (video_dir / name).exists()]
    if missing:
        raise RuntimeError(f"remotion video_dir missing files: {missing}")
    scene_map = json.loads((video_dir / "scenes_map.json").read_text(encoding="utf-8"))
    if not scene_map.get("scenes"):
        raise RuntimeError("scenes_map.json has no scenes")
    segments = json.loads((video_dir / "segments_en.json").read_text(encoding="utf-8")).get("segments", [])
    seg_keys = {s["key"] for s in segments}
    map_keys = {s["key"] for s in scene_map["scenes"]}
    if seg_keys != map_keys:
        raise RuntimeError(f"segments/scenes_map key mismatch: {seg_keys ^ map_keys}")
