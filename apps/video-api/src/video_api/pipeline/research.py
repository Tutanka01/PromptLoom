"""Grounded web research for editorial/cinematic video jobs.

The renderer never accesses the network. This module runs before blueprint
generation, stores a compact source dossier in the job workspace and gives the
LLM bounded excerpts with stable source IDs. Tavily and Exa are deliberately
small adapters over their HTTP APIs; provider credentials stay server-side.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

from video_api.config import Settings
from video_api.documents import Document, DocumentFigure, budget_sections


logger = logging.getLogger(__name__)


class ResearchSource(BaseModel):
    id: str
    title: str = ""
    url: str
    domain: str = ""
    published_at: str | None = None
    excerpt: str = ""
    provider: str


class DossierDocument(BaseModel):
    """The user-supplied document the video explains (see video_api.documents)."""

    id: str
    title: str
    filename: str
    page_count: int
    abstract: str = ""


_DOCUMENT_RULES = (
    "The user supplied the document described in `document`; the video explains THAT document "
    "faithfully to the requested audience. Its sections are the sources with ids doc_NN (web "
    "sources, if any, are src_NN). Base every factual claim, number and definition on these "
    "sources, keep the document's own terminology and notation, and never attribute to it "
    "something it does not say. Attach source_ids to each scene. Never invent a source ID or URL."
)
_FIGURE_RULES = (
    "`figures` lists real figures cropped from the document. Build the explanation around the "
    "2-4 figures that carry the core idea (architecture or pipeline diagrams, key result plots) "
    "with FigureScene, using only listed figure ids. The narration of a FigureScene walks the "
    "viewer through that figure; each callout names one part of it, and uses a listed region id "
    "when the figure has regions."
)


class ResearchDossier(BaseModel):
    query: str
    provider: str
    generated_at: str
    sources: list[ResearchSource] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    document: DossierDocument | None = None
    figures: list[DocumentFigure] = Field(default_factory=list)

    def prompt_context(self, max_chars_per_source: int = 1800, include_figures: bool = True) -> dict[str, Any]:
        """LLM-safe representation: enough evidence to ground a script without
        flooding an 8-12 scene prompt with whole web pages. Document sections
        were already budgeted by attach_document and are passed whole."""
        context: dict[str, Any] = {
            "research_rules": (
                "Use only claims supported by these sources for time-sensitive or factual statements. "
                "Attach source_ids to each scene. Never invent a source ID or URL."
            ),
            "sources": [
                {
                    "id": source.id,
                    "title": source.title,
                    "url": source.url,
                    "published_at": source.published_at,
                    "excerpt": (
                        source.excerpt if source.provider == "document" else source.excerpt[:max_chars_per_source]
                    ),
                }
                for source in self.sources
            ],
        }
        if self.document is not None:
            context["research_rules"] = _DOCUMENT_RULES
            context["document"] = self.document.model_dump()
            if include_figures and self.figures:
                context["research_rules"] += " " + _FIGURE_RULES
                context["figures"] = [
                    {
                        "id": figure.id,
                        "label": figure.label,
                        "page": figure.page,
                        "caption": figure.caption[:500],
                        "aspect_ratio": round(figure.width / max(1, figure.height), 2),
                        **({"description": figure.description} if figure.description else {}),
                        **(
                            {"regions": [{"id": r.id, "label": r.label} for r in figure.regions]}
                            if figure.regions
                            else {}
                        ),
                    }
                    for figure in self.figures
                ]
        return context


def attach_document(dossier: ResearchDossier | None, document: Document, budget_chars: int) -> ResearchDossier:
    """Merge a user document into the job's dossier: its (budgeted) sections
    become doc_NN sources ahead of any web sources, its figures become the
    FigureScene catalogue."""
    doc_sources = [
        ResearchSource(
            id=section.id,
            title=f"{section.heading} (p. {section.page})",
            url=f"document://{document.id}#page={section.page}",
            domain="document",
            excerpt=text,
            provider="document",
        )
        for section, text in budget_sections(document.sections, budget_chars)
    ]
    brief = DossierDocument(
        id=document.id,
        title=document.title,
        filename=document.filename,
        page_count=document.page_count,
        abstract=document.abstract[:2000],
    )
    if dossier is None:
        return ResearchDossier(
            query=document.title,
            provider="document",
            generated_at=datetime.now(timezone.utc).isoformat(),
            sources=doc_sources,
            warnings=list(document.warnings),
            document=brief,
            figures=list(document.figures),
        )
    return dossier.model_copy(
        update={
            "provider": f"document+{dossier.provider}",
            "sources": [*doc_sources, *dossier.sources],
            "warnings": [*document.warnings, *dossier.warnings],
            "document": brief,
            "figures": list(document.figures),
        }
    )


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "PromptLoom/0.1", **headers},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed provider URLs only
            raw = response.read()
    except HTTPError as exc:
        # urllib's default message hides the provider's validation detail,
        # turning an actionable 400 into "Bad Request". The response body is
        # bounded and contains no request headers or API key.
        detail = " ".join(exc.read().decode("utf-8", errors="replace").split())[:800]
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"research provider HTTP {exc.code}{suffix}") from exc
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("research provider returned a non-object response")
    return value


def _clean_text(value: Any, limit: int = 5000) -> str:
    return " ".join(str(value or "").split())[:limit]


def _search_query(value: str, limit: int = 360) -> str:
    """Turn a production brief into a focused web-search query.

    API prompts often contain shot direction, transition notes and style rules.
    Search providers expect a concise information need, and Tavily rejects long
    prompt-shaped queries. Keep the leading topic sentences up to a conservative
    provider-neutral limit, then cut on a word boundary.
    """
    clean = " ".join(str(value or "").split())
    if len(clean) <= limit:
        return clean
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", clean) if part.strip()]
    selected: list[str] = []
    for sentence in sentences:
        candidate = " ".join([*selected, sentence])
        if selected and len(candidate) > limit:
            break
        selected.append(sentence)
        if len(candidate) >= limit:
            break
    compact = " ".join(selected) if selected else clean
    compact = compact[:limit].rsplit(" ", 1)[0].strip() or clean[:limit]
    return compact


def _normalise_sources(rows: list[dict[str, Any]], provider: str, limit: int) -> list[ResearchSource]:
    sources: list[ResearchSource] = []
    seen: set[str] = set()
    for row in rows:
        url = str(row.get("url") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or url in seen:
            continue
        seen.add(url)
        excerpt = _clean_text(
            row.get("raw_content")
            or row.get("text")
            or row.get("content")
            or " ".join(row.get("highlights") or [])
            or row.get("snippet")
        )
        sources.append(
            ResearchSource(
                id=f"src_{len(sources) + 1:02d}",
                title=_clean_text(row.get("title"), 240),
                url=url,
                domain=parsed.netloc.lower(),
                published_at=str(row.get("published_date") or row.get("publishedDate") or "") or None,
                excerpt=excerpt,
                provider=provider,
            )
        )
        if len(sources) >= limit:
            break
    return sources


class Researcher:
    def __init__(self, settings: Settings):
        self.settings = settings

    def research(self, query: str, max_sources: int, required: bool = True) -> ResearchDossier:
        provider = (self.settings.research_provider or "none").strip().lower()
        generated_at = datetime.now(timezone.utc).isoformat()
        if self.settings.fake_llm or provider == "fake":
            return ResearchDossier(
                query=query,
                provider="fake",
                generated_at=generated_at,
                sources=[
                    ResearchSource(
                        id="src_01",
                        title="Deterministic research fixture",
                        url="https://example.invalid/research-fixture",
                        domain="example.invalid",
                        excerpt=f"A deterministic source dossier for: {query}",
                        provider="fake",
                    )
                ],
            )
        if provider == "none":
            message = (
                "research was requested but VIDEO_API_RESEARCH_PROVIDER is not configured "
                "(set exa or tavily plus VIDEO_API_RESEARCH_API_KEY)"
            )
            if required:
                raise RuntimeError(message)
            return ResearchDossier(query=query, provider="none", generated_at=generated_at, warnings=[message])
        if provider not in {"exa", "tavily"}:
            raise RuntimeError(f"unsupported research provider: {provider}")
        if not self.settings.research_api_key:
            message = f"{provider} research requires VIDEO_API_RESEARCH_API_KEY"
            if required:
                raise RuntimeError(message)
            return ResearchDossier(query=query, provider=provider, generated_at=generated_at, warnings=[message])

        search_query = _search_query(query)
        compacted = search_query != " ".join(str(query or "").split())
        logger.info(
            "research.request.start provider=%s prompt_chars=%d query_chars=%d compacted=%s max_sources=%d",
            provider,
            len(query),
            len(search_query),
            compacted,
            max_sources,
        )
        if provider == "tavily":
            data = _post_json(
                "https://api.tavily.com/search",
                {
                    "api_key": self.settings.research_api_key,
                    "query": search_query,
                    "search_depth": "advanced",
                    "max_results": max_sources,
                    "include_raw_content": True,
                },
                {},
                self.settings.research_timeout_seconds,
            )
        else:
            data = _post_json(
                "https://api.exa.ai/search",
                {
                    "query": search_query,
                    "type": "auto",
                    "numResults": max_sources,
                    "contents": {"text": {"maxCharacters": 5000}, "highlights": True},
                },
                {"x-api-key": self.settings.research_api_key},
                self.settings.research_timeout_seconds,
            )
        rows = [row for row in data.get("results", []) if isinstance(row, dict)]
        sources = _normalise_sources(rows, provider, max_sources)
        if required and len(sources) < 3:
            raise RuntimeError(f"{provider} research returned only {len(sources)} usable sources (need at least 3)")
        logger.info("research.request.done provider=%s sources=%d", provider, len(sources))
        return ResearchDossier(
            query=search_query,
            provider=provider,
            generated_at=generated_at,
            sources=sources,
            warnings=(
                ([f"search query compacted from {len(query)} to {len(search_query)} characters"] if compacted else [])
                + ([] if sources else ["research returned no usable sources"])
            ),
        )
