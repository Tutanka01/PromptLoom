# Remotion Scene Archetypes (Lot 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 4 deterministic data-driven Remotion scene archetypes — `QuoteScene`, `SplitFocusScene`, `ZoomNarrativeScene`, `NetworkMapScene` — that the LLM blueprint can compose, reusing the existing cues/captions/transitions/fallback plumbing.

**Architecture:** Each scene is added through the existing data-driven palette: a name in `REMOTION_PALETTE` + `RemotionComponent`, a `_normalise_props` branch (clamps + degrade-to-`BulletScene` fallback) and a `_PALETTE_LINE` entry in `remotion_blueprint.py`, a React component in `scenes/data/scenes.tsx` following the `Shell` + `cueOr` pattern, and a `registry.ts` entry. No `Custom` codegen, no new runtime deps, no asset-resolver changes.

**Tech Stack:** Python 3 (Pydantic, pytest), TypeScript/React, Remotion. Local test venv: `apps/video-api/.venv/bin/pytest`. TS gate: `npx --no-install tsc --noEmit` in `apps/video-api/remotion`.

## Global Constraints

- All scenes 1920×1080. Scene length arrives as the **`dur`** prop; beats run off `p = useCurrentFrame() / dur`. Never use `useVideoConfig().durationInFrames`.
- Never use `@remotion/transitions` / `TransitionSeries` in a scene (overlaps neighbours, desyncs audio). Never self-fade the whole scene — `SceneFrame` owns the entrance/exit envelope. Keep the last beat settled before `p ≈ 0.9`.
- Reveal item `i` via `cueOr(cues, i, fallback)` from `style/anim`. Never hardcode absolute times.
- No broken frames: every `_normalise_props` branch validates required props and falls back to `BulletScene` via `_bullets_from_narration` on invalid input, recording `degrade("…")`.
- React imports only from `react`, `remotion`, and project-internal `../../catalog`, `../../components/primitives`, `../../style/*` (same as existing scenes in `scenes.tsx`).
- Coordinate system (`style/tokens`): `mx(x)=960+x*135`, `my(y)=540-y*135`, `mu(u)=u*135`. Canvas-safe ranges: `x ∈ [-6,6]`, `y ∈ [-3,3]`.
- Each task ends green on `apps/video-api/.venv/bin/pytest -q apps/video-api/tests/test_remotion_engine.py` and commits.

---

## File structure

| File | Responsibility | Tasks |
|---|---|---|
| `apps/video-api/src/video_api/schemas.py` | add 4 names to `REMOTION_PALETTE` + `RemotionComponent` | 1–4 |
| `apps/video-api/src/video_api/pipeline/remotion_blueprint.py` | aliases, `_normalise_props` branches, `_PALETTE_LINE`, NetworkMap layout helper | 1–4 |
| `apps/video-api/remotion/src/scenes/data/scenes.tsx` | the 4 React components | 1–4 |
| `apps/video-api/remotion/src/registry.ts` | register the 4 components | 1–4 |
| `apps/video-api/tests/test_remotion_engine.py` | normalization + parity tests | 1–5 |
| `apps/video-api/docs/remotion-catalog.md`, `remotion-engine.md` | palette docs | 5 |

These 4 tasks edit the same files; **execute sequentially** (no parallel/worktree split).

---

### Task 1: QuoteScene (establishes the vertical slice)

**Files:**
- Modify: `apps/video-api/src/video_api/schemas.py` (`REMOTION_PALETTE`, `RemotionComponent`)
- Modify: `apps/video-api/src/video_api/pipeline/remotion_blueprint.py` (`_COMPONENT_ALIASES`, `_normalise_props`, `_PALETTE_LINE`)
- Modify: `apps/video-api/remotion/src/scenes/data/scenes.tsx`
- Modify: `apps/video-api/remotion/src/registry.ts`
- Test: `apps/video-api/tests/test_remotion_engine.py`

**Interfaces:**
- Consumes: `normalize_remotion_blueprint(raw: dict, target_seconds: int) -> dict`, `_wrap_scene(component, props, narration=None)` (test helper, already present).
- Produces: component name `"QuoteScene"`, props `{quote: str, author?: str, accent?: str}`.

- [ ] **Step 1: Write the failing test**

In `tests/test_remotion_engine.py`, after `test_normalise_new_scenes_empty_fallbacks`:

```python
def test_normalise_quote_scene() -> None:
    out = normalize_remotion_blueprint(
        _wrap_scene("quote", {"quote": "Virtual memory is a useful lie.", "author": "Tanenbaum"}), 240
    )["scenes"][0]
    assert out["component"] == "QuoteScene"  # alias coerced
    assert out["props"]["quote"] == "Virtual memory is a useful lie."
    assert out["props"]["author"] == "Tanenbaum"


def test_normalise_quote_scene_empty_fallback() -> None:
    out = normalize_remotion_blueprint(_wrap_scene("QuoteScene", {}), 240)["scenes"][0]
    # empty quote degrades to a renderable BulletScene, never a blank frame
    assert out["component"] == "BulletScene"
    assert out["props"]["bullets"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `apps/video-api/.venv/bin/pytest -q apps/video-api/tests/test_remotion_engine.py::test_normalise_quote_scene apps/video-api/tests/test_remotion_engine.py::test_normalise_quote_scene_empty_fallback`
Expected: FAIL (`KeyError`/assert: component stays `"BulletScene"` for the alias, or `quote` missing).

- [ ] **Step 3a: Add to the palette (schemas.py)**

Add `"QuoteScene",` to the `REMOTION_PALETTE` tuple and to the `RemotionComponent` Literal (keep ordering near the other content scenes).

- [ ] **Step 3b: Add alias + normalizer branch (remotion_blueprint.py)**

In `_COMPONENT_ALIASES` add:

```python
    "quote": "QuoteScene",
    "quotescene": "QuoteScene",
    "pullquote": "QuoteScene",
```

In `_normalise_props`, add a branch (place it next to the other content branches, before the final `return props`):

```python
    elif component == "QuoteScene":
        quote = str(props.get("quote") or "").strip()
        if len(quote) < 3:
            degrade("QuoteScene without a quote")
            scene["component"] = "BulletScene"
            return {
                "title": props.get("title") or scene.get("title") or "",
                "bullets": _bullets_from_narration(narration, 3),
            }
        props["quote"] = quote[:240]
        author = str(props.get("author") or "").strip()
        if author:
            props["author"] = author[:80]
        else:
            props.pop("author", None)
        return {k: v for k, v in props.items() if k in {"quote", "author", "accent"}}
```

(Use the same `degrade(...)` / `scene["component"] = ...` idiom already used by the `DiagramScene` branch; if `_normalise_props` mutates `scene["component"]` differently, mirror the existing pattern in that file.)

- [ ] **Step 3c: Add the `_PALETTE_LINE` entry (remotion_blueprint.py)**

Append to the `_PALETTE_LINE` string (the LLM-facing signature list):

```
- QuoteScene:   { quote: str, author?: str, accent?: "#hex" }  — a headline quotation/statement (1 beat: quote; +1 if author)
```

- [ ] **Step 4: Run normalization test to verify it passes**

Run: `apps/video-api/.venv/bin/pytest -q apps/video-api/tests/test_remotion_engine.py::test_normalise_quote_scene apps/video-api/tests/test_remotion_engine.py::test_normalise_quote_scene_empty_fallback`
Expected: PASS.

- [ ] **Step 5: Add the React component (scenes.tsx)**

Append to `scenes/data/scenes.tsx` (imports `TextReveal`, `colors`, `fonts`, `mu`, `appear` are already in the file header):

```tsx
/** A headline quotation revealed word-by-word, optional attribution. Full-page. */
export const QuoteScene: React.FC<Base & { quote: string; author?: string }> = ({
  dur,
  accent,
  cues,
  quote = "",
  author,
}) => {
  const { p } = useP(dur);
  const ac = accent ?? colors.user;
  const cQuote = cueOr(cues, 0, 0.12);
  const cAuthor = Math.max(cQuote + 0.1, cueOr(cues, 1, 0.6));
  const size = quote.length > 160 ? 56 : quote.length > 90 ? 72 : 92;
  return (
    <AbsoluteFill>
      <AmbientBackground accent={ac} />
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "0 12%",
          textAlign: "center",
        }}
      >
        <div
          style={{
            fontSize: 180,
            lineHeight: "120px",
            color: ac,
            opacity: appear(p, 0.04, 0.12) * 0.5,
            fontFamily: fonts.sans,
          }}
        >
          “
        </div>
        <TextReveal text={quote} fontSize={size} color={colors.text} delay={cQuote} staggerDelay={0.018} />
        {author ? (
          <div
            style={{
              marginTop: mu(0.5),
              fontSize: 34,
              color: colors.muted,
              opacity: appear(p, cAuthor, cAuthor + 0.1),
              fontFamily: fonts.sans,
            }}
          >
            — {author}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
```

Note: confirm `TextReveal`'s `delay`/`staggerDelay` units against `catalog/text.tsx` (p-ratio vs frames) and adjust the passed values if needed; the `tsc` + smoke gate in Task 5 catches mismatches.

- [ ] **Step 6: Register the component (registry.ts)**

Add `QuoteScene` to the import from `./scenes/data/scenes` and an entry `QuoteScene: QuoteScene as React.FC<Record<string, unknown>>,` to `SCENE_COMPONENTS`.

- [ ] **Step 7: Typecheck the Remotion project**

Run: `cd apps/video-api/remotion && npx --no-install tsc --noEmit`
Expected: exit 0 (no errors).

- [ ] **Step 8: Commit**

```bash
git add apps/video-api/src/video_api/schemas.py apps/video-api/src/video_api/pipeline/remotion_blueprint.py apps/video-api/remotion/src/scenes/data/scenes.tsx apps/video-api/remotion/src/registry.ts apps/video-api/tests/test_remotion_engine.py
git commit -m "feat(remotion): add QuoteScene archetype"
```

---

### Task 2: SplitFocusScene (bounded `kind` panels)

**Files:** same set as Task 1.

**Interfaces:**
- Produces: component `"SplitFocusScene"`, props `{title?, caption?, left: Panel, right: Panel}` where `Panel = {kind, ...}`, `kind ∈ {"code","plot","formula","bullets","terminal"}`.
- Consumes: `sample_expr(expr, lo, hi, n)` (already in `remotion_blueprint.py`) for the `plot` kind's `expr → points`.

- [ ] **Step 1: Write the failing test**

```python
def test_normalise_split_focus_scene() -> None:
    out = normalize_remotion_blueprint(
        _wrap_scene(
            "split",
            {
                "title": "Cause and effect",
                "left": {"kind": "code", "code": "x = 1\n", "lang": "python"},
                "right": {"kind": "bullets", "bullets": ["a", "b"]},
            },
        ),
        240,
    )["scenes"][0]
    assert out["component"] == "SplitFocusScene"
    assert out["props"]["left"]["kind"] == "code"
    assert out["props"]["right"]["kind"] == "bullets"
    assert out["props"]["right"]["bullets"] == ["a", "b"]


def test_normalise_split_focus_plot_expr_to_points() -> None:
    out = normalize_remotion_blueprint(
        _wrap_scene(
            "SplitFocusScene",
            {"left": {"kind": "plot", "expr": "x", "xRange": [-2, 2], "yRange": [-2, 2]},
             "right": {"kind": "formula", "formulas": ["y = x"]}},
        ),
        240,
    )["scenes"][0]
    assert out["component"] == "SplitFocusScene"
    assert "points" in out["props"]["left"] and "expr" not in out["props"]["left"]
    assert out["props"]["right"]["formulas"] == ["y = x"]


def test_normalise_split_focus_invalid_panel_fallback() -> None:
    out = normalize_remotion_blueprint(
        _wrap_scene("split", {"left": {"kind": "image", "src": "x"}, "right": {}}), 240
    )["scenes"][0]
    # no valid bounded panel -> degrade to BulletScene
    assert out["component"] == "BulletScene"
    assert out["props"]["bullets"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `apps/video-api/.venv/bin/pytest -q "apps/video-api/tests/test_remotion_engine.py::test_normalise_split_focus_scene" "apps/video-api/tests/test_remotion_engine.py::test_normalise_split_focus_plot_expr_to_points" "apps/video-api/tests/test_remotion_engine.py::test_normalise_split_focus_invalid_panel_fallback"`
Expected: FAIL.

- [ ] **Step 3a: Palette (schemas.py)** — add `"SplitFocusScene"` to `REMOTION_PALETTE` and `RemotionComponent`.

- [ ] **Step 3b: Aliases + helper + branch (remotion_blueprint.py)**

Aliases:

```python
    "split": "SplitFocusScene",
    "splitfocus": "SplitFocusScene",
    "splitfocusscene": "SplitFocusScene",
    "split_screen": "SplitFocusScene",
```

Module-level helper (near the other `_norm_*` helpers):

```python
_SPLIT_KINDS = ("code", "plot", "formula", "bullets", "terminal")


def _norm_panel(value: Any) -> dict[str, Any] | None:
    """Normalise one SplitFocus panel to a bounded kind, or None if invalid."""
    if not isinstance(value, dict):
        return None
    kind = str(value.get("kind") or "").strip().lower()
    if kind not in _SPLIT_KINDS:
        return None
    if kind == "code":
        code = str(value.get("code") or "").strip()
        if not code:
            return None
        out = {"kind": "code", "code": code[:1200]}
        if value.get("lang"):
            out["lang"] = str(value["lang"])[:24]
        if value.get("codeTitle"):
            out["codeTitle"] = str(value["codeTitle"])[:60]
        return out
    if kind == "terminal":
        command = str(value.get("command") or value.get("cmd") or "").strip()
        if not command:
            return None
        out = {"kind": "terminal", "command": command[:200]}
        if value.get("output"):
            out["output"] = str(value["output"])[:400]
        return out
    if kind == "formula":
        formulas = [str(f).strip() for f in (value.get("formulas") or []) if str(f).strip()]
        if not formulas:
            return None
        return {"kind": "formula", "formulas": formulas[:2]}
    if kind == "bullets":
        bullets = [str(b).strip() for b in (value.get("bullets") or []) if str(b).strip()]
        if not bullets:
            return None
        out = {"kind": "bullets", "bullets": bullets[:4]}
        if value.get("heading"):
            out["heading"] = str(value["heading"])[:60]
        return out
    if kind == "plot":
        x_range = _clamp_range(value.get("xRange"), -50, 50, (-4.0, 4.0))
        y_range = _clamp_range(value.get("yRange"), -200, 200, (-2.0, 6.0))
        expr = value.get("expr")
        pts = value.get("points")
        if expr:
            pts = sample_expr(str(expr), x_range[0], x_range[1], n=80)
        if not isinstance(pts, list) or not pts:
            return None
        out = {"kind": "plot", "points": pts, "xRange": x_range, "yRange": y_range}
        if value.get("xLabel"):
            out["xLabel"] = str(value["xLabel"])[:24]
        if value.get("yLabel"):
            out["yLabel"] = str(value["yLabel"])[:24]
        return out
    return None
```

Branch in `_normalise_props`:

```python
    elif component == "SplitFocusScene":
        left = _norm_panel(props.get("left"))
        right = _norm_panel(props.get("right"))
        if left is None or right is None:
            degrade("SplitFocusScene without two valid panels")
            scene["component"] = "BulletScene"
            return {
                "title": props.get("title") or scene.get("title") or "",
                "bullets": _bullets_from_narration(narration, 4),
            }
        out = {"left": left, "right": right}
        if props.get("title"):
            out["title"] = str(props["title"])[:80]
        if props.get("caption"):
            out["caption"] = str(props["caption"])[:120]
        return out
```

- [ ] **Step 3c: `_PALETTE_LINE`**

```
- SplitFocusScene: { title?: str, left: Panel, right: Panel, caption?: str } where Panel = { kind: "code"|"plot"|"formula"|"bullets"|"terminal", ... } — two live panels side by side (beats: left, right, then inner items)
```

- [ ] **Step 4: Run to verify pass** — same command as Step 2. Expected: PASS.

- [ ] **Step 5: React component (scenes.tsx)**

```tsx
type SplitPanel =
  | { kind: "code"; code: string; lang?: string; codeTitle?: string }
  | { kind: "plot"; points: [number, number][]; xRange: [number, number]; yRange: [number, number]; xLabel?: string; yLabel?: string }
  | { kind: "formula"; formulas: string[] }
  | { kind: "bullets"; bullets: string[]; heading?: string }
  | { kind: "terminal"; command: string; output?: string };

const fnFromPoints = (points: [number, number][]) => (x: number): number => {
  if (points.length === 0) return 0;
  if (x <= points[0][0]) return points[0][1];
  for (let i = 1; i < points.length; i++) {
    if (x <= points[i][0]) {
      const [x0, y0] = points[i - 1];
      const [x1, y1] = points[i];
      const t = (x - x0) / (x1 - x0 || 1);
      return y0 + t * (y1 - y0);
    }
  }
  return points[points.length - 1][1];
};

const Panel: React.FC<{ panel: SplitPanel; p: number; start: number; accent: string }> = ({ panel, p, start, accent }) => {
  const reveal = appear(p, start, start + 0.12);
  if (panel.kind === "code") {
    return (
      <div style={{ opacity: reveal }}>
        <CodeBlock code={panel.code} lang={panel.lang ?? "python"} fontSize={26} startAt={start} title={panel.codeTitle} accent={accent} />
      </div>
    );
  }
  if (panel.kind === "terminal") {
    const typed = beat(p, start, start + 0.3, "linear");
    return <Terminal x={0} y={0} w={6.2} h={3.6} text={`$ ${panel.command}\n${panel.output ?? ""}`} typed={typed} opacity={reveal} />;
  }
  if (panel.kind === "formula") {
    return (
      <div style={{ opacity: reveal, display: "flex", flexDirection: "column", gap: 28, alignItems: "center", justifyContent: "center", height: "100%" }}>
        {panel.formulas.map((tex, i) => (
          <MathFormula key={i} tex={tex} display fontSize={48} color={colors.text} delay={start + i * 0.12} />
        ))}
      </div>
    );
  }
  if (panel.kind === "bullets") {
    return (
      <div style={{ opacity: reveal, display: "flex", flexDirection: "column", gap: 22, justifyContent: "center", height: "100%", padding: "0 6%" }}>
        {panel.heading ? <div style={{ fontSize: 36, fontWeight: 700, color: accent, fontFamily: fonts.sans }}>{panel.heading}</div> : null}
        {panel.bullets.map((b, i) => (
          <div key={i} style={{ fontSize: 32, color: colors.text, opacity: appear(p, start + 0.1 + i * 0.1, start + 0.2 + i * 0.1), fontFamily: fonts.sans }}>
            • {b}
          </div>
        ))}
      </div>
    );
  }
  // plot
  return (
    <div style={{ opacity: reveal, display: "flex", alignItems: "center", justifyContent: "center", height: "100%" }}>
      <Plot
        fn={fnFromPoints(panel.points)}
        xRange={panel.xRange}
        yRange={panel.yRange}
        width={760}
        height={520}
        color={accent}
        drawProgress={beat(p, start, start + 0.33)}
        xLabel={panel.xLabel ?? "x"}
        yLabel={panel.yLabel ?? "y"}
      />
    </div>
  );
};

/** Two live panels side by side (cause/effect, code + its result). */
export const SplitFocusScene: React.FC<Base & { left: SplitPanel; right: SplitPanel }> = ({ dur, accent, title, caption, cues, left, right }) => {
  const { p } = useP(dur);
  const ac = accent ?? colors.user;
  const cLeft = cueOr(cues, 0, 0.14);
  const cRight = Math.max(cLeft + 0.05, cueOr(cues, 1, 0.4));
  return (
    <Shell dur={dur} accent={ac} title={title} caption={caption}>
      <div style={{ position: "absolute", left: 0, top: my(1.6), width: WIDTH, display: "flex", gap: 0 }}>
        <div style={{ width: WIDTH / 2, height: mu(5.2), position: "relative", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Panel panel={left} p={p} start={cLeft} accent={ac} />
        </div>
        <div style={{ width: WIDTH / 2, height: mu(5.2), position: "relative", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Panel panel={right} p={p} start={cRight} accent={colors.success} />
        </div>
      </div>
      <div style={{ position: "absolute", left: WIDTH / 2 - 1, top: my(1.5), width: 2, height: mu(5.2), background: colors.edge, opacity: 0.5 }} />
    </Shell>
  );
};
```

Add `beat` to the `style/anim` import line at the top of `scenes.tsx` (currently `import { appear, cueOr, dimAt, lastCue } from "../../style/anim";` → add `beat`). Confirm `CodeBlock`/`MathFormula` prop names against `catalog/`; adjust if `tsc` complains.

- [ ] **Step 6: Register** — add `SplitFocusScene` to the import + `SCENE_COMPONENTS` in `registry.ts`.

- [ ] **Step 7: Typecheck** — `cd apps/video-api/remotion && npx --no-install tsc --noEmit` → exit 0.

- [ ] **Step 8: Commit**

```bash
git add apps/video-api/src apps/video-api/remotion/src apps/video-api/tests
git commit -m "feat(remotion): add SplitFocusScene archetype (bounded kinds)"
```

---

### Task 3: ZoomNarrativeScene (semantic camera)

**Files:** same set as Task 1.

**Interfaces:**
- Produces: component `"ZoomNarrativeScene"`, props `{canvas: [{id, label, x, y, sub?, detail?}], path: [str], accent?}` (normalizer always emits a resolved `path`).

- [ ] **Step 1: Failing test**

```python
def test_normalise_zoom_narrative_scene() -> None:
    out = normalize_remotion_blueprint(
        _wrap_scene(
            "zoom",
            {"canvas": [
                {"id": "a", "label": "Process", "x": -3, "y": 1, "detail": "PID, state"},
                {"id": "b", "label": "Kernel", "x": 3, "y": -1},
                {"id": "c", "label": "Hardware", "x": 0, "y": -2.5}],
             "path": ["a", "b", "x-unknown"]},
        ),
        240,
    )["scenes"][0]
    assert out["component"] == "ZoomNarrativeScene"
    assert [n["id"] for n in out["props"]["canvas"]] == ["a", "b", "c"]
    # unknown id dropped, unvisited "c" appended -> every id visited once
    assert out["props"]["path"] == ["a", "b", "c"]
    assert -6 <= out["props"]["canvas"][0]["x"] <= 6


def test_normalise_zoom_narrative_too_few_items_fallback() -> None:
    out = normalize_remotion_blueprint(_wrap_scene("ZoomNarrativeScene", {"canvas": [{"id": "a", "label": "x"}]}), 240)["scenes"][0]
    assert out["component"] == "BulletScene"
    assert out["props"]["bullets"]
```

- [ ] **Step 2: Run to verify fail.**
Run: `apps/video-api/.venv/bin/pytest -q "apps/video-api/tests/test_remotion_engine.py::test_normalise_zoom_narrative_scene" "apps/video-api/tests/test_remotion_engine.py::test_normalise_zoom_narrative_too_few_items_fallback"`
Expected: FAIL.

- [ ] **Step 3a: Palette (schemas.py)** — add `"ZoomNarrativeScene"`.

- [ ] **Step 3b: Aliases + branch (remotion_blueprint.py)**

Aliases:

```python
    "zoom": "ZoomNarrativeScene",
    "zoomnarrative": "ZoomNarrativeScene",
    "zoomnarrativescene": "ZoomNarrativeScene",
    "canvas": "ZoomNarrativeScene",
```

Branch:

```python
    elif component == "ZoomNarrativeScene":
        raw_items = props.get("canvas") if isinstance(props.get("canvas"), list) else []
        items: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for i, it in enumerate(raw_items[:8]):
            if not isinstance(it, dict):
                continue
            iid = str(it.get("id") or f"n{i}").strip()[:24]
            if not iid or iid in seen_ids:
                continue
            seen_ids.add(iid)
            node = {
                "id": iid,
                "label": str(it.get("label") or iid)[:48],
                "x": max(-6.0, min(6.0, float(it.get("x", 0) or 0))),
                "y": max(-3.0, min(3.0, float(it.get("y", 0) or 0))),
            }
            if it.get("sub"):
                node["sub"] = str(it["sub"])[:48]
            if it.get("detail"):
                node["detail"] = str(it["detail"])[:120]
            items.append(node)
        if len(items) < 2:
            degrade("ZoomNarrativeScene with fewer than 2 canvas items")
            scene["component"] = "BulletScene"
            return {
                "title": props.get("title") or scene.get("title") or "",
                "bullets": _bullets_from_narration(narration, 4),
            }
        raw_path = props.get("path") if isinstance(props.get("path"), list) else []
        path: list[str] = []
        for pid in raw_path:
            sid = str(pid).strip()
            if sid in seen_ids and sid not in path:
                path.append(sid)
        for node in items:  # append any unvisited node, preserving canvas order
            if node["id"] not in path:
                path.append(node["id"])
        out = {"canvas": items, "path": path}
        if props.get("accent"):
            out["accent"] = str(props["accent"])
        return out
```

- [ ] **Step 3c: `_PALETTE_LINE`**

```
- ZoomNarrativeScene: { canvas: [{id, label, x(-6..6), y(-3..3), sub?, detail?}], path?: [id], accent? } — camera zooms/pans across a canvas; one beat per path stop (+1 overview)
```

- [ ] **Step 4: Run to verify pass** (Step 2 command). Expected: PASS.

- [ ] **Step 5: React component (scenes.tsx)**

```tsx
type CanvasItem = { id: string; label: string; x: number; y: number; sub?: string; detail?: string };

/** Camera that zooms/pans across a virtual canvas, revealing detail per stop. */
export const ZoomNarrativeScene: React.FC<Base & { canvas: CanvasItem[]; path: string[] }> = ({ dur, accent, title, cues, canvas, path }) => {
  const { p } = useP(dur);
  const ac = accent ?? colors.user;
  const byId = Object.fromEntries(canvas.map((c) => [c.id, c]));
  const stops = path.map((id) => byId[id]).filter(Boolean) as CanvasItem[];
  // camera keyframes: each stop at its cue; final keyframe = overview (scale 1, centred)
  const cueAt = (i: number) => cueOr(cues, i, 0.12 + (i * (0.82 - 0.12)) / Math.max(1, stops.length));
  const times: number[] = stops.map((_, i) => cueAt(i));
  times.push(0.92); // overview
  const ZOOM = 1.9;
  const targetsX = stops.map((s) => s.x).concat([0]);
  const targetsY = stops.map((s) => s.y).concat([0]);
  const scales = stops.map(() => ZOOM).concat([1]);
  const camX = interpolate(p, times, targetsX, { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const camY = interpolate(p, times, targetsY, { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const scale = interpolate(p, times, scales, { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  // world transform: translate so (camX,camY) sits at screen centre, then scale about centre
  const tx = -(camX) * mu(1) * scale;
  const ty = (camY) * mu(1) * scale;
  return (
    <AbsoluteFill>
      <AmbientBackground accent={ac} />
      {title ? <TitleBar label={title} opacity={appear(p, 0, 0.08)} /> : null}
      <AbsoluteFill style={{ transform: `translate(${tx}px, ${ty}px) scale(${scale})`, transformOrigin: "center center" }}>
        {canvas.map((item, i) => {
          const stopIdx = path.indexOf(item.id);
          const reveal = appear(p, cueAt(Math.max(0, stopIdx)), cueAt(Math.max(0, stopIdx)) + 0.1);
          return (
            <div key={item.id} style={{ opacity: 0.35 + 0.65 * reveal }}>
              <Card x={item.x} y={item.y} w={2.4} h={1.2} accent={ac} glow={reveal} fontPx={30}>
                <div>
                  {item.label}
                  {item.sub ? <div style={{ fontSize: 20, color: colors.muted }}>{item.sub}</div> : null}
                </div>
              </Card>
              {item.detail ? (
                <Caption x={item.x} y={item.y - 0.95} label={item.detail} color={colors.muted} size={18} opacity={reveal} width={3} />
              ) : null}
            </div>
          );
        })}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
```

Note: `interpolate` requires strictly increasing `times`; the normalizer dedups path, but if two cues resolve equal at render time, clamp with `Math.max(prev+0.001, t)` when building `times`. Add that guard if the smoke render warns.

- [ ] **Step 6: Register** — `ZoomNarrativeScene` in `registry.ts`.

- [ ] **Step 7: Typecheck** — exit 0.

- [ ] **Step 8: Commit**

```bash
git add apps/video-api/src apps/video-api/remotion/src apps/video-api/tests
git commit -m "feat(remotion): add ZoomNarrativeScene archetype"
```

---

### Task 4: NetworkMapScene (deterministic Python layout)

**Files:** same set as Task 1, plus the layout helper in `remotion_blueprint.py`.

**Interfaces:**
- Produces: component `"NetworkMapScene"`, props `{nodes: [{id, label, x, y, group?}], links: [{a, b, label?}]}` — `x/y` are computed in Python (LLM never supplies them).

- [ ] **Step 1: Failing test**

```python
def test_normalise_network_map_scene_layout_is_deterministic() -> None:
    raw = _wrap_scene(
        "network",
        {"nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
         "links": [{"a": "a", "b": "b"}, {"a": "b", "b": "z-missing"}]},
    )
    out1 = normalize_remotion_blueprint(raw, 240)["scenes"][0]
    out2 = normalize_remotion_blueprint(raw, 240)["scenes"][0]
    assert out1["component"] == "NetworkMapScene"
    # positions assigned, in-bounds, deterministic
    assert all(-6 <= n["x"] <= 6 and -3 <= n["y"] <= 3 for n in out1["props"]["nodes"])
    assert [(n["x"], n["y"]) for n in out1["props"]["nodes"]] == [(n["x"], n["y"]) for n in out2["props"]["nodes"]]
    # link to a missing node id dropped
    assert out1["props"]["links"] == [{"a": "a", "b": "b"}]


def test_normalise_network_map_empty_fallback() -> None:
    out = normalize_remotion_blueprint(_wrap_scene("NetworkMapScene", {"nodes": []}), 240)["scenes"][0]
    assert out["component"] == "BulletScene"
    assert out["props"]["bullets"]
```

- [ ] **Step 2: Run to verify fail.**
Run: `apps/video-api/.venv/bin/pytest -q "apps/video-api/tests/test_remotion_engine.py::test_normalise_network_map_scene_layout_is_deterministic" "apps/video-api/tests/test_remotion_engine.py::test_normalise_network_map_empty_fallback"`
Expected: FAIL.

- [ ] **Step 3a: Palette (schemas.py)** — add `"NetworkMapScene"`.

- [ ] **Step 3b: Layout helper + branch (remotion_blueprint.py)**

At module top, ensure `import math` is present (add if missing). Helper near the other `_norm_*` helpers:

```python
def _network_layout(n: int) -> list[tuple[float, float]]:
    """Deterministic golden-angle spiral placement, squashed to 16:9 and scaled
    to the canvas bounds. Same n -> same coordinates (render determinism)."""
    if n <= 0:
        return []
    if n == 1:
        return [(0.0, 0.0)]
    golden = math.pi * (3.0 - math.sqrt(5.0))  # ~2.39996 rad
    radius = min(5.0, 1.6 + n * 0.18)
    out: list[tuple[float, float]] = []
    for i in range(n):
        r = radius * math.sqrt((i + 0.5) / n)
        a = i * golden
        x = round(max(-6.0, min(6.0, r * math.cos(a))), 3)
        y = round(max(-3.0, min(3.0, r * 0.62 * math.sin(a))), 3)
        out.append((x, y))
    return out
```

Aliases:

```python
    "network": "NetworkMapScene",
    "networkmap": "NetworkMapScene",
    "networkmapscene": "NetworkMapScene",
    "graph": "NetworkMapScene",
```

Branch:

```python
    elif component == "NetworkMapScene":
        raw_nodes = props.get("nodes") if isinstance(props.get("nodes"), list) else []
        nodes: list[dict[str, Any]] = []
        ids: set[str] = set()
        for i, nd in enumerate(raw_nodes[:10]):
            if not isinstance(nd, dict):
                continue
            nid = str(nd.get("id") or f"n{i}").strip()[:24]
            if not nid or nid in ids:
                continue
            ids.add(nid)
            node = {"id": nid, "label": str(nd.get("label") or nid)[:40]}
            if nd.get("group"):
                node["group"] = str(nd["group"])[:24]
            nodes.append(node)
        if not nodes:
            degrade("NetworkMapScene without nodes")
            scene["component"] = "BulletScene"
            return {
                "title": props.get("title") or scene.get("title") or "",
                "bullets": _bullets_from_narration(narration, 4),
            }
        coords = _network_layout(len(nodes))
        for node, (x, y) in zip(nodes, coords):
            node["x"], node["y"] = x, y
        raw_links = props.get("links") if isinstance(props.get("links"), list) else []
        links: list[dict[str, Any]] = []
        for lk in raw_links[:20]:
            if not isinstance(lk, dict):
                continue
            a, b = str(lk.get("a") or "").strip(), str(lk.get("b") or "").strip()
            if a in ids and b in ids and a != b:
                link = {"a": a, "b": b}
                if lk.get("label"):
                    link["label"] = str(lk["label"])[:32]
                links.append(link)
        return {"nodes": nodes, "links": links}
```

- [ ] **Step 3c: `_PALETTE_LINE`**

```
- NetworkMapScene: { nodes: [{id, label, group?}], links: [{a, b, label?}] } — animated graph; positions are auto-computed (do NOT provide x/y); one beat per node
```

- [ ] **Step 4: Run to verify pass** (Step 2 command). Expected: PASS.

- [ ] **Step 5: React component (scenes.tsx)**

```tsx
type NetNode = { id: string; label: string; x: number; y: number; group?: string };
type NetLink = { a: string; b: string; label?: string };

const GROUP_COLORS = [colors.user, colors.success, colors.purple ?? colors.user, colors.kernel ?? colors.success];

/** Animated node-link graph; nodes light up on cue, edges draw after both ends. */
export const NetworkMapScene: React.FC<Base & { nodes: NetNode[]; links: NetLink[] }> = ({ dur, accent, title, caption, cues, nodes, links }) => {
  const { p } = useP(dur);
  const ac = accent ?? colors.user;
  const idx = Object.fromEntries(nodes.map((n, i) => [n.id, i]));
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const groups = Array.from(new Set(nodes.map((n) => n.group ?? "_")));
  const colorFor = (n: NetNode) => GROUP_COLORS[groups.indexOf(n.group ?? "_") % GROUP_COLORS.length] ?? ac;
  const nodeCue = (i: number) => cueOr(cues, i, 0.12 + (i * 0.6) / Math.max(1, nodes.length));
  return (
    <Shell dur={dur} accent={ac} title={title} caption={caption}>
      {links.map((lk, i) => {
        const a = byId[lk.a];
        const b = byId[lk.b];
        if (!a || !b) return null;
        const start = Math.max(nodeCue(idx[lk.a] ?? 0), nodeCue(idx[lk.b] ?? 0));
        const progress = beat(p, start, start + 0.16, "linear");
        return <Arrow key={`l${i}`} from={[a.x, a.y]} to={[b.x, b.y]} color={colors.edge} width={2.5} progress={progress} opacity={0.7} />;
      })}
      {nodes.map((n, i) => {
        const reveal = appear(p, nodeCue(i), nodeCue(i) + 0.1);
        return (
          <div key={n.id} style={{ opacity: reveal, transform: `scale(${0.85 + 0.15 * reveal})`, transformOrigin: `${mx(n.x)}px ${my(n.y)}px` }}>
            <Card x={n.x} y={n.y} w={1.8} h={0.8} accent={colorFor(n)} glow={reveal * 0.8} fontPx={22}>
              {n.label}
            </Card>
          </div>
        );
      })}
    </Shell>
  );
};
```

Confirm `colors.purple` / `colors.kernel` exist in `style/tokens.ts`; if not, replace the `GROUP_COLORS` entries with existing color keys (the `?? colors.user` guards already cover absence at value level, but the keys must exist for `tsc`).

- [ ] **Step 6: Register** — `NetworkMapScene` in `registry.ts`.

- [ ] **Step 7: Typecheck** — exit 0.

- [ ] **Step 8: Commit**

```bash
git add apps/video-api/src apps/video-api/remotion/src apps/video-api/tests
git commit -m "feat(remotion): add NetworkMapScene archetype with deterministic layout"
```

---

### Task 5: Parity test, docs, and full verification

**Files:**
- Test: `apps/video-api/tests/test_remotion_engine.py`
- Modify: `apps/video-api/docs/remotion-catalog.md`, `apps/video-api/docs/remotion-engine.md`

**Interfaces:** consumes `REMOTION_PALETTE` (schemas) and `SCENE_COMPONENTS` (registry.ts text).

- [ ] **Step 1: Parity test (every palette name is registered + advertised)**

```python
def test_new_archetypes_registered_and_advertised() -> None:
    from video_api.schemas import REMOTION_PALETTE
    from video_api.pipeline.remotion_blueprint import _PALETTE_LINE
    registry_src = (REMOTION_DIR / "src" / "registry.ts").read_text()
    for name in ("QuoteScene", "SplitFocusScene", "ZoomNarrativeScene", "NetworkMapScene"):
        assert name in REMOTION_PALETTE, f"{name} missing from REMOTION_PALETTE"
        assert f"{name}:" in registry_src, f"{name} missing from registry.ts"
        assert name in _PALETTE_LINE, f"{name} missing from the LLM palette prompt"
```

- [ ] **Step 2: Run parity test**
Run: `apps/video-api/.venv/bin/pytest -q "apps/video-api/tests/test_remotion_engine.py::test_new_archetypes_registered_and_advertised"`
Expected: PASS (fix any gap it reports).

- [ ] **Step 3: Update docs**

In `docs/remotion-engine.md` "Palette de composants testés" table and `docs/remotion-catalog.md` "Data-driven scene palette" table, add the four rows:

- `QuoteScene` — `quote, author?, accent?`
- `SplitFocusScene` — `title?, left{kind,…}, right{kind,…}, caption?` (kinds: code|plot|formula|bullets|terminal)
- `ZoomNarrativeScene` — `canvas[{id,label,x,y,sub?,detail?}], path?, accent?`
- `NetworkMapScene` — `nodes[{id,label,group?}], links[{a,b,label?}]` (x/y auto-computed)

- [ ] **Step 4: Full Python test suite**
Run: `apps/video-api/.venv/bin/pytest -q apps/video-api/tests/test_remotion_engine.py`
Expected: all PASS (including `test_remotion_project_typechecks`).

- [ ] **Step 5: Light checks from repo root**

```bash
python3 -m py_compile $(find apps/video-api/src apps/video-api/tests -name '*.py' -print)
docker compose config --quiet
git diff --check
git status --short
```

Expected: no errors.

- [ ] **Step 6: Smoke render exercising all 4 scenes**

Build a tiny blueprint that uses the four scenes and render at draft quality in Docker (the rendering path is in scope):

```bash
docker compose run --rm \
  -e VIDEO_API_RENDER_ENGINE=remotion \
  -e QUALITY=ql \
  test apps/video-api/.venv/bin/pytest -q apps/video-api/tests/test_remotion_engine.py
```

Then a manual end-to-end smoke (optional but recommended): POST a job whose prompt naturally yields a quote/graph/split, confirm a terminal `done` status, download the MP4, and inspect a few frames (ffprobe + 3 snapshots) per the project's verify routine. Confirm no black/frozen frames.

- [ ] **Step 7: Commit**

```bash
git add apps/video-api/tests apps/video-api/docs
git commit -m "test+docs(remotion): parity guard and catalog entries for new archetypes"
```

---

## Self-Review

**Spec coverage:** QuoteScene (T1), SplitFocusScene with bounded kinds + image excluded (T2), ZoomNarrativeScene with LLM-supplied coords (T3), NetworkMapScene with Python deterministic layout (T4), cues ordering documented per scene in each `_PALETTE_LINE` (T1–T4), fallbacks + clamps (every branch), tests + docs + parity + smoke render (T5). All spec sections map to a task.

**Placeholder scan:** No TBD/TODO. Two engineering notes (verify `TextReveal` delay units; verify `colors.purple/kernel`/`CodeBlock` prop names) are guarded by the `tsc` gate, not missing logic.

**Type consistency:** `normalize_remotion_blueprint(raw, target_seconds)`, `_norm_panel`, `_network_layout(n)`, `cueOr`, `appear`, `beat`, `Card`/`Arrow`/`Terminal`/`Plot`/`MathFormula`/`CodeBlock` prop names match the code read during design. `_PALETTE_LINE` and `REMOTION_PALETTE` names are identical across tasks and guarded by T5.
