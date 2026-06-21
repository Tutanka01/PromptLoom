"""Deterministic stock-media acquisition and provenance manifest.

Blueprints request an asset by semantic query; they never provide a URL. The
worker resolves that query through an allow-listed provider, downloads the file
before rendering and rewrites the scene props to a job-local path. A failed
asset request degrades to a tested BulletScene rather than a broken/blank frame.
"""
from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

from video_api.config import Settings


logger = logging.getLogger(__name__)
MEDIA_COMPONENTS = {"ImageScene": "image", "FootageScene": "video"}


class AssetRecord(BaseModel):
    scene_key: str
    kind: str
    query: str
    status: str
    local_path: str | None = None
    source_url: str | None = None
    source_page: str | None = None
    author: str | None = None
    license: str | None = None
    provider: str
    sha256: str | None = None
    warning: str | None = None


class AssetManifest(BaseModel):
    provider: str
    assets: list[AssetRecord] = Field(default_factory=list)


def _read_json(url: str, api_key: str, timeout: float) -> dict[str, Any]:
    request = Request(
        url,
        headers={"Authorization": api_key, "User-Agent": "PromptLoom/0.1"},
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed Pexels endpoint
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("asset provider returned a non-object response")
    return value


def _allowed_pexels_download(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (host == "pexels.com" or host.endswith(".pexels.com"))


def _download(url: str, destination: Path, timeout: float, max_bytes: int) -> tuple[str, str]:
    if not _allowed_pexels_download(url):
        raise RuntimeError("provider returned a download URL outside the Pexels domain allow-list")
    request = Request(url, headers={"User-Agent": "PromptLoom/0.1"})
    digest = hashlib.sha256()
    total = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urlopen(request, timeout=timeout) as response, destination.open("wb") as handle:  # noqa: S310
            content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0]
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise RuntimeError(f"asset exceeds download cap ({max_bytes // (1024 * 1024)} MB)")
                digest.update(chunk)
                handle.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    if total == 0:
        raise RuntimeError("asset download was empty")
    return digest.hexdigest(), content_type


def _fallback_scene(scene: Any, warning: str) -> None:
    from video_api.pipeline.remotion_blueprint import _bullets_from_narration

    scene.component = "BulletScene"
    scene.props = {
        "title": scene.title,
        "bullets": _bullets_from_narration(scene.narration, 4),
        "caption": "Visual source unavailable — diagrammatic fallback",
    }
    scene.visual_intent = f"{scene.visual_intent} Fallback reason: {warning}"[:600]


class AssetResolver:
    def __init__(self, settings: Settings):
        self.settings = settings

    def resolve(self, blueprint: Any, workspace: Path, *, allow_stock: bool, max_assets: int) -> AssetManifest:
        provider = (self.settings.asset_provider or "none").strip().lower()
        output_dir = workspace / "assets"
        output_dir.mkdir(parents=True, exist_ok=True)
        records: list[AssetRecord] = []
        used = 0
        for scene in blueprint.scenes:
            kind = MEDIA_COMPONENTS.get(scene.component)
            if not kind:
                continue
            query = " ".join(str(scene.props.get("asset_query") or scene.title).split())[:180]
            if not allow_stock:
                warning = "stock media disabled by production policy"
                _fallback_scene(scene, warning)
                records.append(AssetRecord(scene_key=scene.key, kind=kind, query=query, status="fallback", provider=provider, warning=warning))
                continue
            if used >= max_assets:
                warning = f"asset budget exhausted (max_assets={max_assets})"
                _fallback_scene(scene, warning)
                records.append(AssetRecord(scene_key=scene.key, kind=kind, query=query, status="fallback", provider=provider, warning=warning))
                continue
            if provider != "pexels" or not self.settings.pexels_api_key:
                warning = "Pexels provider/key is not configured"
                _fallback_scene(scene, warning)
                records.append(AssetRecord(scene_key=scene.key, kind=kind, query=query, status="fallback", provider=provider, warning=warning))
                continue
            try:
                record = self._resolve_pexels(scene, query, kind, output_dir)
                records.append(record)
                used += 1
            except Exception as exc:
                warning = str(exc)
                logger.warning("asset.resolve.failed scene=%s kind=%s error=%s", scene.key, kind, exc)
                _fallback_scene(scene, warning)
                records.append(AssetRecord(scene_key=scene.key, kind=kind, query=query, status="fallback", provider=provider, warning=warning))
        manifest = AssetManifest(provider=provider, assets=records)
        (workspace / "asset_manifest.json").write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
        logger.info("asset.resolve.done requested=%d acquired=%d fallback=%d", len(records), used, len(records) - used)
        return manifest

    def _resolve_pexels(self, scene: Any, query: str, kind: str, output_dir: Path) -> AssetRecord:
        endpoint = "videos/search" if kind == "video" else "v1/search"
        data = _read_json(
            f"https://api.pexels.com/{endpoint}?query={quote_plus(query)}&orientation=landscape&per_page=8",
            self.settings.pexels_api_key,
            self.settings.research_timeout_seconds,
        )
        if kind == "video":
            rows = [row for row in data.get("videos", []) if isinstance(row, dict)]
            if not rows:
                raise RuntimeError("Pexels returned no matching video")
            selected = rows[0]
            files = [
                item
                for item in selected.get("video_files", [])
                if isinstance(item, dict) and item.get("link")
            ]
            # Prefer a landscape MP4 close to 1080p. Picking the largest file
            # often selects a multi-hundred-megabyte 4K master that then trips
            # the download cap without adding visible quality to a 1080p render.
            files.sort(
                key=lambda item: (
                    str(item.get("file_type") or "") == "video/mp4",
                    int(item.get("width") or 0) >= 1280,
                    -abs(int(item.get("width") or 0) - 1920),
                    -abs(int(item.get("height") or 0) - 1080),
                ),
                reverse=True,
            )
            if not files:
                raise RuntimeError("Pexels video has no downloadable files")
            media_url = str(files[0]["link"])
            page = str(selected.get("url") or "")
            author = str((selected.get("user") or {}).get("name") or "")
            scene.props["mediaDurationSeconds"] = max(1.0, float(selected.get("duration") or 8.0))
            extension = Path(urlparse(media_url).path).suffix or ".mp4"
        else:
            rows = [row for row in data.get("photos", []) if isinstance(row, dict)]
            if not rows:
                raise RuntimeError("Pexels returned no matching image")
            selected = rows[0]
            sources = selected.get("src") or {}
            # large2x is normally around the useful 1080p range and avoids
            # downloading an oversized camera original for every still.
            media_url = str(
                sources.get("large2x")
                or sources.get("landscape")
                or sources.get("large")
                or sources.get("original")
                or ""
            )
            page = str(selected.get("url") or "")
            author = str(selected.get("photographer") or "")
            extension = Path(urlparse(media_url).path).suffix or ".jpg"
        safe_ext = extension.lower() if extension.lower() in {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov"} else (".mp4" if kind == "video" else ".jpg")
        filename = f"{scene.key}-{hashlib.sha256(query.encode()).hexdigest()[:10]}{safe_ext}"
        destination = output_dir / filename
        digest, content_type = _download(
            media_url,
            destination,
            self.settings.research_timeout_seconds,
            self.settings.asset_max_download_mb * 1024 * 1024,
        )
        expected = "video/" if kind == "video" else "image/"
        guessed = mimetypes.guess_type(destination.name)[0] or content_type
        if not (content_type.startswith(expected) or guessed.startswith(expected)):
            destination.unlink(missing_ok=True)
            raise RuntimeError(f"downloaded media has unexpected content type: {content_type or guessed}")
        scene.props["src"] = f"assets/{filename}"
        scene.props["credit"] = f"{author} / Pexels" if author else "Pexels"
        scene.props.setdefault("motion", "ken-burns" if kind == "image" else "push-in")
        return AssetRecord(
            scene_key=scene.key,
            kind=kind,
            query=query,
            status="acquired",
            local_path=str(destination),
            source_url=media_url,
            source_page=page,
            author=author or None,
            license="Pexels License",
            provider="pexels",
            sha256=digest,
        )
