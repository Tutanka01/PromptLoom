import React from "react";
import { AbsoluteFill, Img, Loop, OffthreadVideo, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { AmbientBackground } from "../../catalog/AmbientBackground";
import { MathFormula } from "../../catalog/MathFormula";
import { CodeBlock } from "../../catalog/CodeBlock";
import { Plot } from "../../catalog/Plot";
import { TextReveal, BlurReveal } from "../../catalog/text";
import { MemoryGrid, type MemoryCell } from "../../catalog/MemoryGrid";
import { FlowToken } from "../../catalog/FlowToken";
import { BarChart, type Bar, type BarSeries } from "../../catalog/BarChart";
import { Counter } from "../../catalog/Counter";
import { Icon } from "../../catalog/Icon";
import { Arrow, Caption, Card, FitText, Terminal, TitleBar, Zone } from "../../components/primitives";
import { fitText, fitTogether } from "../../style/fit";
import { alpha, colors, fonts, HEIGHT, mu, mx, my, PX_PER_UNIT, WIDTH } from "../../style/tokens";
import { appear, beat, cueOr, dimAt, lastCue } from "../../style/anim";

/**
 * Data-driven STEM scene templates. Each reads plain props (no code) so a
 * blueprint produced by the LLM — or a deterministic builder — can render a real
 * video by *composing the tested library*. `dur` is the scene's length in
 * frames (injected by MainComposition); beats are driven off p = frame / dur.
 *
 * Beat/cue helpers come from `style/anim` (smoothstep easing, shared with the
 * Custom-scene barrel). Each scene fades its content IN at the start and OUT
 * near the end; the composition's persistent AmbientBackground shows through the
 * dip, so scenes cross-dissolve over a continuous background.
 *
 * `cues` (optional) holds narration-synced reveal ratios per visual item,
 * resolved by the pipeline from the word-level alignment of the TTS audio
 * (pipeline/beats.py). `null` entries fall back to the default even spacing.
 */

type Base = { dur: number; accent?: string; title?: string; caption?: string; cues?: (number | null)[] };

const useP = (dur: number) => {
  const frame = useCurrentFrame();
  return { frame, p: frame / dur };
};

// The vertical band free for a scene's content, in px: below the title bar and
// above the caption line (or the bottom margin when the scene has no caption).
// Content laid out inside it can never collide with either.
const STAGE_TOP = 175;
const stageBottom = (caption?: string): number => (caption ? 900 : 990);
// The scene-to-scene envelope (fade/slide/wipe in and out) is owned by the
// composition's SceneFrame — scenes only animate their own content.

const Shell: React.FC<Base & { children: React.ReactNode; accentDefault?: string }> = ({
  dur,
  accent,
  title,
  caption,
  children,
  accentDefault = colors.user,
}) => {
  const { p } = useP(dur);
  const ac = accent ?? accentDefault;
  return (
    <AbsoluteFill>
      <AmbientBackground accent={ac} />
      {title ? <TitleBar label={title} opacity={appear(p, 0, 0.08)} /> : null}
      {children}
      {caption ? (
        <Caption x={0} y={-3.05} label={caption} color={colors.muted} size={28} opacity={appear(p, 0.55, 0.68)} width={13} />
      ) : null}
    </AbsoluteFill>
  );
};

/** Big title + subtitle. Use to open a video or a section. */
export const TitleScene: React.FC<Base & { subtitle?: string }> = ({ dur, accent, title = "", subtitle }) => {
  const { frame, p } = useP(dur);
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
      <AmbientBackground accent={accent ?? colors.purple} />
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 30 }}>
        <TextReveal text={title} fontSize={84} color={colors.text} staggerDelay={4} />
        {subtitle ? (
          <div style={{ opacity: appear(p, 0.25, 0.4) }}>
            <BlurReveal text={subtitle} fontSize={40} color={colors.muted} delay={Math.round(0.25 * dur)} />
          </div>
        ) : null}
      </div>
      <div style={{ position: "absolute", bottom: 120, width: 280, height: 4, borderRadius: 2, background: accent ?? colors.purple, opacity: interpolate(frame, [0, 20], [0, 0.8], { extrapolateRight: "clamp" }) }} />
    </AbsoluteFill>
  );
};

/** Title + staggered bullet points. Use for definitions, properties, steps. */
export const BulletScene: React.FC<Base & { bullets: string[]; icons?: (string | null)[] }> = ({ dur, accent, title, caption, cues, bullets, icons }) => {
  const { p } = useP(dur);
  const ac = accent ?? colors.user;
  const items = bullets.slice(0, 6);
  // One size for the whole list: the largest at which every bullet fits on
  // two lines. The block is centred in the stage (text stays left-aligned).
  const textW = 1440;
  const size = fitTogether(items, { width: textW, maxLines: 2, max: 38, min: 28, weight: 500 }).fontSize;
  const lineH = size * 1.25;
  const bottom = stageBottom(caption);
  return (
    <Shell dur={dur} accent={ac} title={title} caption={caption}>
      <div style={{ position: "absolute", left: 0, width: WIDTH, top: STAGE_TOP, height: bottom - STAGE_TOP, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 34, maxWidth: textW + 60 }}>
          {items.map((b, i, arr) => {
            const start = cueOr(cues, i, 0.12 + i * 0.12);
            const enter = appear(p, start, start + 0.1);
            // Focus the bullet currently being spoken: once the NEXT bullet
            // appears, gently dim this one so attention follows the narration
            // while the whole list stays readable. The last bullet stays bright.
            const isLast = i === arr.length - 1;
            const focus = isLast ? 1 : dimAt(p, cueOr(cues, i + 1, start + 0.12), 0.6);
            const icon = icons?.[i];
            return (
              <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 22, opacity: enter * focus, transform: `translateX(${interpolate(enter, [0, 1], [-30, 0])}px)` }}>
                {icon ? (
                  <div style={{ marginTop: (lineH - 34) / 2, flexShrink: 0, display: "flex" }}>
                    <Icon name={icon} size={34} color={ac} />
                  </div>
                ) : (
                  <div style={{ width: 16, height: 16, marginTop: (lineH - 16) / 2, borderRadius: 4, background: ac, flexShrink: 0, transform: "rotate(45deg)" }} />
                )}
                <span style={{ color: colors.text, fontFamily: fonts.sans, fontSize: size, lineHeight: 1.25, fontWeight: 500, textWrap: "pretty" }}>{b}</span>
              </div>
            );
          })}
        </div>
      </div>
    </Shell>
  );
};

/** Title + up to 3 LaTeX formulas stepping in. Use for math/derivations. */
export const FormulaScene: React.FC<Base & { formulas: string[] }> = ({ dur, accent, title, caption, cues, formulas }) => {
  const { p } = useP(dur);
  return (
    <Shell dur={dur} accent={accent ?? colors.kernel} title={title} caption={caption} accentDefault={colors.kernel}>
      <div style={{ position: "absolute", left: 0, width: 1920, top: my(2.3), height: my(-2.5) - my(2.3), display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 40 }}>
        {formulas.slice(0, 3).map((tex, i, arr) => {
          const start = cueOr(cues, i, 0.12 + i * 0.2);
          const enter = appear(p, start, start + 0.12);
          // Dim each derivation step once the next one appears; the final line
          // (the result) stays bright — classic focus/dim for a derivation.
          const isLast = i === arr.length - 1;
          const focus = isLast ? 1 : dimAt(p, cueOr(cues, i + 1, 0.12 + (i + 1) * 0.2), 0.5);
          return (
            <div key={i} style={{ opacity: enter * focus }}>
              <MathFormula tex={tex} fontSize={i === 0 ? 54 : 44} color={isLast ? (accent ?? colors.kernel) : colors.text} delay={Math.round(start * dur)} />
            </div>
          );
        })}
      </div>
    </Shell>
  );
};

/** Title + syntax-highlighted code revealed line by line. Use for CS/algorithms. */
export const CodeScene: React.FC<Base & { code: string; lang?: string; codeTitle?: string }> = ({ dur, accent, title, caption, cues, code, lang = "python", codeTitle }) => {
  const startP = cueOr(cues, 0, 0.12);
  return (
    <Shell dur={dur} accent={accent ?? colors.purple} title={title} caption={caption} accentDefault={colors.purple}>
      <div style={{ position: "absolute", left: 0, width: 1920, top: my(1.4), display: "flex", justifyContent: "center" }}>
        <CodeBlock code={code} lang={lang} title={codeTitle} startAt={Math.round(startP * dur)} lineReveal={Math.max(4, Math.round(0.05 * dur))} fontSize={30} accent={accent ?? colors.purple} />
      </div>
    </Shell>
  );
};

/** Axes + one or several curves, with optional sweep, area and named markers.
 * Single-curve mode: `points` (+ sweep/area). Multi-curve mode: `curves`
 * (supply/demand, compared functions) each revealed on its own cue, then
 * `markers` (equilibrium/intersection) with dashed guides to the axes. */
export const PlotScene: React.FC<
  Base & {
    points?: [number, number][];
    curves?: { points: [number, number][]; label?: string; color?: string; dash?: boolean }[];
    markers?: { x: number; y: number; label?: string; color?: string; guides?: boolean }[];
    xRange: [number, number];
    yRange?: [number, number];
    xLabel?: string;
    yLabel?: string;
    sweep?: boolean;
    area?: boolean;
    color?: string;
  }
> = ({ dur, accent, title, caption, cues, points, curves, markers, xRange, yRange, xLabel, yLabel, sweep = false, area = false, color }) => {
  const { p } = useP(dur);
  const clamp = { extrapolateLeft: "clamp" as const, extrapolateRight: "clamp" as const };

  if (curves && curves.length > 0) {
    // cues[i] = curve i drawn while spoken; next cue = markers revealed.
    const starts = curves.map((_, i) => cueOr(cues, i, 0.12 + i * 0.18));
    const series = curves.map((c, i) => ({
      points: c.points,
      label: c.label,
      color: c.color,
      dash: c.dash,
      drawProgress: interpolate(p, [starts[i], starts[i] + 0.28], [0, 1], clamp),
    }));
    const lastStart = starts[starts.length - 1];
    const cMark = Math.max(lastStart + 0.2, cueOr(cues, curves.length, 0.62));
    const marks = (markers ?? []).map((m, i) => ({
      ...m,
      guides: m.guides ?? true,
      progress: appear(p, cMark + i * 0.06, cMark + i * 0.06 + 0.1),
    }));
    return (
      <Shell dur={dur} accent={accent ?? colors.success} title={title} caption={caption} accentDefault={colors.success}>
        <div style={{ position: "absolute", left: 0, width: 1920, top: my(1.7), display: "flex", justifyContent: "center" }}>
          <Plot series={series} markers={marks} xRange={xRange} yRange={yRange} width={1000} height={580} xLabel={xLabel ?? "x"} yLabel={yLabel ?? "y"} />
        </div>
      </Shell>
    );
  }

  // cues[0] = curve drawn while spoken; cues[1] = sweep/area while spoken.
  const c0 = cueOr(cues, 0, 0.12);
  const c1 = Math.max(c0 + 0.1, cueOr(cues, 1, 0.5));
  const draw = interpolate(p, [c0, c0 + 0.33], [0, 1], clamp);
  const fn = fnFromPoints(points ?? []);
  const sweepX = sweep ? interpolate(p, [c1, Math.min(0.95, c1 + 0.4)], [xRange[0], xRange[1]], clamp) : null;
  const areaTo = area ? interpolate(p, [c1, Math.min(0.92, c1 + 0.35)], [xRange[0], xRange[1]], clamp) : null;
  const marks = (markers ?? []).map((m, i) => ({
    ...m,
    guides: m.guides ?? true,
    progress: appear(p, c1 + i * 0.06, c1 + i * 0.06 + 0.1),
  }));
  return (
    <Shell dur={dur} accent={accent ?? colors.success} title={title} caption={caption} accentDefault={colors.success}>
      <div style={{ position: "absolute", left: 0, width: 1920, top: my(1.7), display: "flex", justifyContent: "center" }}>
        <Plot
          fn={fn}
          xRange={xRange}
          yRange={yRange}
          width={1000}
          height={580}
          color={color ?? colors.success}
          drawProgress={draw}
          tangentAt={sweepX}
          pointAt={sweepX}
          areaTo={areaTo}
          markers={marks}
          xLabel={xLabel ?? "x"}
          yLabel={yLabel ?? "y"}
        />
      </div>
    </Shell>
  );
};

type NodeBox = { x: number; y: number; w: number; h: number; fontSize: number; start: number };

/** Where the segment from `box`'s centre along (dx, dy) leaves the box (plus a
 * small margin), so an arrow starts/ends on the card border, not under it. */
const exitPoint = (box: NodeBox, dx: number, dy: number): [number, number] => {
  const hw = box.w / 2 + 0.08;
  const hh = box.h / 2 + 0.08;
  const t = Math.min(dx ? hw / Math.abs(dx) : Infinity, dy ? hh / Math.abs(dy) : Infinity);
  return [box.x + dx * t, box.y + dy * t];
};

/** General node-edge diagram (systems, processes, relationships). x,y in Manim units. */
export const DiagramScene: React.FC<
  Base & {
    nodes: { id: string; label: string; x: number; y: number; color?: string; icon?: string }[];
    edges: { from: string; to: string; color?: string; label?: string }[];
  }
> = ({ dur, accent, title, caption, cues, nodes, edges }) => {
  const { p } = useP(dur);
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  // Each card is sized to its label, never wider than the gap to its nearest
  // neighbour on the same row, and kept between the title bar and the caption.
  const yTop = (HEIGHT / 2 - STAGE_TOP) / PX_PER_UNIT;
  const yBottom = (HEIGHT / 2 - stageBottom(caption)) / PX_PER_UNIT;
  const boxes: Record<string, NodeBox> = {};
  nodes.forEach((n, i) => {
    let room = 3.4;
    for (const o of nodes) {
      if (o !== n && Math.abs(o.y - n.y) < 1.3) room = Math.min(room, Math.abs(o.x - n.x) - 0.3);
    }
    const maxW = Math.max(1.5, room);
    const fit = fitText(n.label, { width: mu(maxW) - 34, maxLines: 3, max: 26, min: 17, lineHeight: 1.15 });
    const w = Math.min(maxW, Math.max(1.8, (fit.width + 44) / PX_PER_UNIT));
    const h = Math.max(1.0, ((n.icon ? 34 : 0) + fit.lines * fit.fontSize * 1.15 + 32) / PX_PER_UNIT);
    boxes[n.id] = {
      x: Math.max(-6.9 + w / 2, Math.min(6.9 - w / 2, n.x)),
      y: Math.max(yBottom + h / 2, Math.min(yTop - h / 2, n.y)),
      w,
      h,
      fontSize: fit.fontSize,
      start: cueOr(cues, i, 0.12 + i * 0.08),
    };
  });
  return (
    <Shell dur={dur} accent={accent ?? colors.user} title={title} caption={caption}>
      {edges.map((e, i) => {
        const a = boxes[e.from];
        const b = boxes[e.to];
        if (!a || !b) return null;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const from = exitPoint(a, dx, dy);
        const to = exitPoint(b, -dx, -dy);
        // Overlapping cards: no room for an arrow between them.
        if ((to[0] - from[0]) * dx + (to[1] - from[1]) * dy <= 0) return null;
        // An edge never draws toward a node that hasn't appeared yet (cues can
        // reorder node reveals relative to the default grid).
        const start = Math.max(0.3 + i * 0.06, b.start + 0.04);
        const prog = interpolate(p, [start, start + 0.1], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        const color = e.color ?? colors.muted;
        const label = (e.label ?? "").trim();
        const lengthPx = mu(Math.hypot(to[0] - from[0], to[1] - from[1]));
        const labelFit = label ? fitText(label, { width: Math.max(150, Math.min(320, lengthPx * 0.9)), maxLines: 2, max: 21, min: 15 }) : null;
        return (
          <React.Fragment key={i}>
            <Arrow from={from} to={to} color={color} width={3} progress={prog} />
            {label && labelFit ? (
              <div
                style={{
                  position: "absolute",
                  left: mx((from[0] + to[0]) / 2),
                  top: my((from[1] + to[1]) / 2),
                  transform: "translate(-50%, -50%)",
                  width: labelFit.width + 4,
                  padding: "4px 12px",
                  boxSizing: "content-box",
                  borderRadius: 10,
                  background: colors.bg,
                  border: `1px solid ${colors.edge}`,
                  color: colors.text,
                  fontFamily: fonts.sans,
                  fontSize: labelFit.fontSize,
                  fontWeight: 600,
                  lineHeight: 1.15,
                  textAlign: "center",
                  textWrap: "balance",
                  opacity: appear(p, start + 0.06, start + 0.12),
                }}
              >
                {label}
              </div>
            ) : null}
          </React.Fragment>
        );
      })}
      {nodes.map((n) => {
        const box = boxes[n.id];
        const s = spring({ frame: frame - Math.round(box.start * dur), fps, config: { damping: 14, stiffness: 120 } });
        const color = n.color ?? colors.user;
        return (
          <div key={n.id} style={{ transform: `scale(${s})`, transformOrigin: `${mx(box.x)}px ${my(box.y)}px` }}>
            <Card x={box.x} y={box.y} w={box.w} h={box.h} accent={color} opacity={interpolate(p, [box.start, box.start + 0.08], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })} fontPx={box.fontSize}>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
                {n.icon ? <Icon name={n.icon} size={28} color={color} /> : null}
                <div style={{ width: mu(box.w) - 34, fontSize: box.fontSize, lineHeight: 1.15, textWrap: "balance", overflowWrap: "anywhere" }}>{n.label}</div>
              </div>
            </Card>
          </div>
        );
      })}
    </Shell>
  );
};

const LAYER_COLORS = [colors.user, colors.success, colors.kernel, colors.hardware, colors.purple];

/** Two-column comparison: user vs kernel, before vs after, pros vs cons. */
export const ComparisonScene: React.FC<
  Base & {
    left: { label: string; items: string[] };
    right: { label: string; items: string[] };
  }
> = ({ dur, accent, title, caption, cues, left, right }) => {
  const { p } = useP(dur);
  const colW = 770;
  const leftItems = (left.items ?? []).slice(0, 5);
  const rightItems = (right.items ?? []).slice(0, 5);
  // Both columns share one item size and one header size, so they read as a pair.
  const itemSize = fitTogether([...leftItems, ...rightItems], { width: colW - 110, maxLines: 3, max: 31, min: 24, weight: 500 }).fontSize;
  const headSize = fitTogether([left.label, right.label], { width: colW, maxLines: 1, max: 32, min: 24, weight: 700 }).fontSize;
  const bottom = stageBottom(caption);
  // Cue order matches the blueprint contract: all left items, then all right
  // items. Each column's zone/header leads its first cued item slightly.
  const column = (side: { label: string }, items: string[], color: string, base: number, offset: number, col: 1 | 2) => {
    const firstCue = cues?.[offset];
    const zoneStart = firstCue != null ? Math.max(0.03, firstCue - 0.08) : base;
    const zone = appear(p, zoneStart, zoneStart + 0.1);
    return (
      <>
        <div style={{ gridColumn: col, gridRow: 1, textAlign: "center", opacity: zone, color, fontFamily: fonts.sans, fontSize: headSize, fontWeight: 700, whiteSpace: "nowrap" }}>
          {side.label}
        </div>
        {/* Sized to its content (rows stretch both zones to the same height). */}
        <div
          style={{
            gridColumn: col,
            gridRow: 2,
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            gap: 26,
            padding: "40px 44px",
            borderRadius: mu(0.16),
            border: `2px solid ${color}`,
            background: alpha(color, 0.07),
            opacity: zone,
          }}
        >
          {items.map((it, i) => {
            const start = cueOr(cues, offset + i, base + 0.14 + i * 0.1);
            const op = appear(p, start, start + 0.1);
            return (
              <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 16, opacity: op, transform: `translateY(${(1 - op) * 10}px)` }}>
                <div style={{ width: 12, height: 12, marginTop: (itemSize * 1.25 - 12) / 2, borderRadius: 3, background: color, flexShrink: 0, transform: "rotate(45deg)" }} />
                <span style={{ color: colors.text, fontFamily: fonts.sans, fontSize: itemSize, fontWeight: 500, lineHeight: 1.25, textWrap: "pretty" }}>{it}</span>
              </div>
            );
          })}
        </div>
      </>
    );
  };
  return (
    <Shell dur={dur} accent={accent ?? colors.user} title={title} caption={caption}>
      <div
        style={{
          position: "absolute",
          left: (WIDTH - 2 * colW - 70) / 2,
          width: 2 * colW + 70,
          top: STAGE_TOP,
          height: bottom - STAGE_TOP,
          display: "grid",
          gridTemplateColumns: `${colW}px ${colW}px`,
          gridTemplateRows: "auto auto",
          columnGap: 70,
          rowGap: 22,
          alignContent: "center",
        }}
      >
        {column(left, leftItems, accent ?? colors.user, 0.1, 0, 1)}
        {column(right, rightItems, colors.kernel, 0.22, leftItems.length, 2)}
      </div>
    </Shell>
  );
};

/** Stacked system layers (app -> syscall -> kernel -> hardware), top to bottom. */
export const LayeredSystemScene: React.FC<
  Base & { layers: { label: string; sub?: string; color?: string }[] }
> = ({ dur, accent, title, caption, cues, layers }) => {
  const { p } = useP(dur);
  const items = (layers ?? []).slice(0, 5);
  const n = Math.max(1, items.length);
  const top = 1.9;
  const bottom = -2.5;
  const gap = 0.32;
  const bandH = (top - bottom - gap * (n - 1)) / n;
  const textW = mu(9.2) - 70;
  return (
    <Shell dur={dur} accent={accent ?? colors.user} title={title} caption={caption}>
      {items.map((layer, i) => {
        const cy = top - bandH / 2 - i * (bandH + gap);
        const start = cueOr(cues, i, 0.12 + i * 0.12);
        const op = appear(p, start, start + 0.12);
        const color = layer.color ?? LAYER_COLORS[i % LAYER_COLORS.length];
        // Label and sub share one line when they fit; otherwise the sub goes
        // under the label (bands are tall enough), both fitted to the band.
        const oneLine = layer.sub ? `${layer.label}   ${layer.sub}` : layer.label;
        const inline = fitText(oneLine, { width: textW, maxLines: 1, max: 34, min: 26, weight: 700 }).fits;
        return (
          <React.Fragment key={i}>
            <Zone x={0} y={cy} w={9.2} h={bandH} color={color} fill={alpha(color, 0.09)} opacity={op} />
            <div
              style={{
                position: "absolute",
                left: mx(-4.6),
                width: mu(9.2),
                top: my(cy + bandH / 2),
                height: mu(bandH),
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 2,
                opacity: op,
              }}
            >
              {inline ? (
                <div style={{ display: "flex", alignItems: "baseline", gap: 16, whiteSpace: "nowrap" }}>
                  <span style={{ color: colors.text, fontFamily: fonts.sans, fontSize: 34, fontWeight: 700 }}>{layer.label}</span>
                  {layer.sub ? <span style={{ color: colors.muted, fontFamily: fonts.sans, fontSize: 24 }}>{layer.sub}</span> : null}
                </div>
              ) : (
                <>
                  <FitText text={layer.label} width={textW} maxLines={1} max={32} min={22} weight={700} />
                  {layer.sub ? (
                    <FitText text={layer.sub} width={textW} maxLines={1} max={23} min={17} weight={400} color={colors.muted} />
                  ) : null}
                </>
              )}
            </div>
            {i < items.length - 1 ? (
              <Arrow from={[0, cy - bandH / 2]} to={[0, cy - bandH / 2 - gap]} color={colors.muted} width={3} progress={appear(p, start + 0.08, start + 0.16)} />
            ) : null}
          </React.Fragment>
        );
      })}
    </Shell>
  );
};

/** Left-to-right sequence of steps along a baseline (process / lifecycle). */
export const TimelineScene: React.FC<
  Base & { steps: { label: string; sub?: string }[] }
> = ({ dur, accent, title, caption, cues, steps }) => {
  const { p } = useP(dur);
  const items = (steps ?? []).slice(0, 5);
  const n = Math.max(1, items.length);
  const ac = accent ?? colors.user;
  const x0 = -5;
  const x1 = 5;
  const span = n > 1 ? (x1 - x0) / (n - 1) : 0;
  // A label never spills into its neighbour's slot.
  const labelW = mu(Math.min(3.0, n > 1 ? span - 0.2 : 6));
  const labelSize = fitTogether(items.map((st) => st.label), { width: labelW, maxLines: 3, max: 26, min: 18 }).fontSize;
  return (
    <Shell dur={dur} accent={ac} title={title} caption={caption}>
      <Arrow from={[x0 - 0.5, 0]} to={[x1 + 0.5, 0]} color={colors.edge} width={3} progress={appear(p, 0.1, 0.3)} />
      {items.map((step, i) => {
        const cx = n > 1 ? x0 + i * span : 0;
        const start = cueOr(cues, i, 0.2 + i * 0.14);
        const op = appear(p, start, start + 0.12);
        const focus = i === items.length - 1 ? 1 : dimAt(p, cueOr(cues, i + 1, start + 0.14), 0.55);
        return (
          <React.Fragment key={i}>
            {/* Dim with brightness, not opacity: a translucent card would let
                the baseline arrow show through it. */}
            <div style={{ opacity: op, filter: focus < 1 ? `brightness(${focus})` : undefined }}>
              <Card x={cx} y={0} w={1.5} h={1.0} accent={ac} fontPx={30}>{`${i + 1}`}</Card>
            </div>
            <div style={{ position: "absolute", left: mx(cx) - labelW / 2, top: my(-0.9), width: labelW, textAlign: "center", opacity: op }}>
              <div style={{ color: colors.text, fontFamily: fonts.sans, fontSize: labelSize, fontWeight: 600, lineHeight: 1.2, textWrap: "balance", overflowWrap: "anywhere" }}>{step.label}</div>
              {step.sub ? <FitText text={step.sub} width={labelW} maxLines={2} max={20} min={15} weight={400} color={colors.muted} style={{ marginTop: 6 }} /> : null}
            </div>
          </React.Fragment>
        );
      })}
    </Shell>
  );
};

/** A shell command typed out, with its output below (CLI / syscall demos). */
export const TerminalScene: React.FC<Base & { command: string; output?: string }> = ({
  dur,
  accent,
  title,
  caption,
  cues,
  command,
  output,
}) => {
  const { p } = useP(dur);
  // cues[0] = command typed while spoken; cues[1] = output revealed while spoken.
  const c0 = cueOr(cues, 0, 0.12);
  const c1 = Math.max(c0 + 0.12, cueOr(cues, 1, 0.55));
  const typed = interpolate(p, [c0, c0 + 0.38], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <Shell dur={dur} accent={accent ?? colors.user} title={title} caption={caption}>
      <Terminal x={0} y={1.15} w={11} h={1.1} text={`$ ${command}`} typed={typed} opacity={appear(p, Math.max(0.03, c0 - 0.06), c0 + 0.04)} />
      {output ? (
        <div
          style={{
            position: "absolute",
            left: mx(-5.5),
            top: my(0.2),
            width: mu(11),
            opacity: appear(p, c1, c1 + 0.15),
            fontFamily: fonts.mono,
            fontSize: 26,
            lineHeight: 1.5,
            color: colors.muted,
            whiteSpace: "pre-line",
          }}
        >
          {output}
        </div>
      ) : null}
    </Shell>
  );
};

/** A grid of labelled cells: memory, page tables, registers, stack frames. */
export const MemoryScene: React.FC<Base & { cells: MemoryCell[]; cols?: number }> = ({ dur, accent, title, caption, cues, cells, cols }) => {
  const { p } = useP(dur);
  const ac = accent ?? colors.user;
  // The grid reveals progressively from the first spoken cue to the last.
  const c0 = cueOr(cues, 0, 0.12);
  const cEnd = Math.max(c0 + 0.15, lastCue(cues, 0.7));
  return (
    <Shell dur={dur} accent={ac} title={title} caption={caption}>
      <MemoryGrid cells={cells} cols={cols ?? 4} x={0} y={0.1} reveal={appear(p, c0, cEnd)} accent={ac} />
    </Shell>
  );
};

/** A packet travelling left-to-right through a row of stages (data flow / syscall path). */
export const FlowScene: React.FC<Base & { stages: { label: string; sub?: string; icon?: string }[] }> = ({ dur, accent, title, caption, cues, stages }) => {
  const { p } = useP(dur);
  const items = (stages ?? []).slice(0, 5);
  const n = Math.max(1, items.length);
  const ac = accent ?? colors.success;
  const x0 = -5;
  const x1 = 5;
  const span = n > 1 ? (x1 - x0) / (n - 1) : 0;
  const xs = items.map((_, i) => (n > 1 ? x0 + i * span : 0));
  const y = 0.2;
  // The token's journey spans first-cue -> last-cue, so it sits on the stage
  // currently being narrated instead of sweeping at a fixed pace.
  const t0 = cueOr(cues, 0, 0.22);
  const t1 = Math.max(t0 + 0.2, lastCue(cues, 0.9));
  const travel = appear(p, t0, t1); // 0..1 across the whole row
  const segF = travel * (n - 1);
  const seg = Math.max(0, Math.min(n - 2, Math.floor(segF)));
  const segP = n > 1 ? segF - seg : 0;
  const active = Math.min(n - 1, Math.round(travel * (n - 1)));
  // Cards and their sub-captions stay inside their own slot; one label size
  // for every stage, fitted to the card (icon above the label).
  const cardW = n > 1 ? Math.min(2.2, span - 0.4) : 2.4;
  const labelW = mu(cardW) - 26;
  const hasIcon = items.some((st) => st.icon);
  const labelFit = fitTogether(items.map((st) => st.label), { width: labelW, maxLines: hasIcon ? 2 : 3, max: 24, min: 16, lineHeight: 1.15 });
  const labelSize = labelFit.fontSize;
  const cardH = Math.max(1.0, ((hasIcon ? 32 : 0) + labelFit.lines * labelSize * 1.15 + 30) / PX_PER_UNIT);
  const subW = n > 1 ? Math.min(2.6, span - 0.15) : 3;
  return (
    <Shell dur={dur} accent={ac} title={title} caption={caption}>
      {items.slice(0, -1).map((_, i) => (
        <Arrow key={i} from={[xs[i] + cardW / 2 + 0.05, y]} to={[xs[i + 1] - cardW / 2 - 0.05, y]} color={colors.edge} width={3} progress={appear(p, 0.1, 0.25)} />
      ))}
      {items.map((st, i) => {
        const op = appear(p, 0.12 + i * 0.06, 0.22 + i * 0.06);
        return (
          <React.Fragment key={i}>
            <div style={{ opacity: op }}>
              <Card x={xs[i]} y={y} w={cardW} h={cardH} accent={ac} glow={i === active ? 0.85 : 0} fontPx={labelSize}>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
                  {st.icon ? <Icon name={st.icon} size={26} color={ac} /> : null}
                  <div style={{ width: labelW, fontSize: labelSize, lineHeight: 1.15, textWrap: "balance", overflowWrap: "anywhere" }}>{st.label}</div>
                </div>
              </Card>
            </div>
            {st.sub ? <Caption x={xs[i]} y={y - cardH / 2 - 0.45} label={st.sub} color={colors.muted} size={20} width={subW} opacity={op} /> : null}
          </React.Fragment>
        );
      })}
      {n > 1 ? <FlowToken from={[xs[seg], y + cardH / 2 + 0.35]} to={[xs[seg + 1], y + cardH / 2 + 0.35]} progress={segP} color={ac} opacity={appear(p, 0.2, 0.3)} /> : null}
    </Shell>
  );
};

/** Animated bar chart for quantities / benchmarks / comparisons. Simple
 * (`bars`) or grouped (`groups` x `series`, with a legend). Each category
 * grows on its own narration cue. */
export const BarChartScene: React.FC<Base & { bars?: Bar[]; groups?: string[]; series?: BarSeries[]; unit?: string }> = ({
  dur,
  accent,
  title,
  caption,
  cues,
  bars,
  groups,
  series,
  unit,
}) => {
  const { p } = useP(dur);
  const grouped = Boolean(groups && groups.length && series && series.length);
  const n = Math.max(1, grouped ? groups!.length : (bars ?? []).length);
  let prev = -1;
  const reveal = Array.from({ length: n }, (_, i) => {
    // Cues keep their spoken order; a missing cue falls back to an even stagger.
    const start = Math.max(prev + 0.03, cueOr(cues, i, 0.15 + (i * 0.45) / Math.max(1, n - 1)));
    prev = start;
    return appear(p, start, start + 0.1);
  });
  const width = 1480;
  const bottom = stageBottom(caption);
  return (
    <Shell dur={dur} accent={accent ?? colors.user} title={title} caption={caption}>
      <div style={{ position: "absolute", left: (WIDTH - width) / 2, top: STAGE_TOP + 20, width, height: bottom - STAGE_TOP - 20 }}>
        <BarChart bars={bars} groups={groups} series={series} unit={unit} reveal={reveal} width={width} height={bottom - STAGE_TOP - 20} />
      </div>
    </Shell>
  );
};

/** A single big animated number for a metric (throughput, size, count, latency). */
export const CounterScene: React.FC<
  Base & { value: number; prefix?: string; suffix?: string; label?: string; decimals?: number }
> = ({ dur, accent, title, caption, value, prefix, suffix, label, decimals }) => {
  const { p } = useP(dur);
  const ac = accent ?? colors.kernel;
  return (
    <Shell dur={dur} accent={ac} title={title} caption={caption} accentDefault={colors.kernel}>
      <div style={{ position: "absolute", left: 0, width: WIDTH, top: my(0.7), display: "flex", flexDirection: "column", alignItems: "center", gap: 24 }}>
        <Counter value={value} progress={appear(p, 0.15, 0.7)} prefix={prefix} suffix={suffix} decimals={decimals ?? 0} color={ac} />
        {label ? (
          <span style={{ color: colors.text, fontFamily: fonts.sans, fontSize: 36, fontWeight: 600, opacity: appear(p, 0.3, 0.5) }}>{label}</span>
        ) : null}
      </div>
    </Shell>
  );
};

type MediaBase = Base & {
  src: string;
  credit?: string;
  motion?: "ken-burns" | "pan-left" | "pan-right" | "push-in" | "static";
};

const mediaTransform = (p: number, motion: MediaBase["motion"]): string => {
  if (motion === "static") return "scale(1.02)";
  const zoom = interpolate(p, [0, 1], motion === "ken-burns" ? [1.04, 1.16] : [1.03, 1.10]);
  const dx = motion === "pan-left" ? interpolate(p, [0, 1], [30, -30]) : motion === "pan-right" ? interpolate(p, [0, 1], [-30, 30]) : 0;
  return `translateX(${dx}px) scale(${zoom})`;
};

const MediaChrome: React.FC<MediaBase & {children: React.ReactNode}> = ({dur, title, caption, credit, accent, children}) => {
  const {p} = useP(dur);
  return (
    <AbsoluteFill style={{backgroundColor: colors.bg, overflow: "hidden"}}>
      {children}
      <AbsoluteFill style={{background: "linear-gradient(180deg, rgba(5,8,13,.74) 0%, rgba(5,8,13,.06) 36%, rgba(5,8,13,.18) 62%, rgba(5,8,13,.86) 100%)"}} />
      {title ? <TitleBar label={title} opacity={appear(p, 0.02, 0.1)} /> : null}
      {caption ? <Caption x={0} y={-2.75} label={caption} color={colors.text} size={31} opacity={appear(p, 0.56, 0.68)} width={11.5} /> : null}
      {credit ? (
        <div style={{position: "absolute", right: 42, bottom: 28, color: "rgba(236,241,248,.62)", fontFamily: fonts.sans, fontSize: 18}}>
          {credit}
        </div>
      ) : null}
      <div style={{position: "absolute", left: 0, bottom: 0, width: `${interpolate(p, [0, 1], [0, 100])}%`, height: 4, background: accent ?? colors.user, opacity: .72}} />
    </AbsoluteFill>
  );
};

/** Licensed still with deterministic editorial camera movement. */
export const ImageScene: React.FC<MediaBase> = ({dur, src, motion = "ken-burns", ...rest}) => {
  const {p} = useP(dur);
  return (
    <MediaChrome dur={dur} src={src} motion={motion} {...rest}>
      <Img
        src={staticFile(src)}
        style={{width: "100%", height: "100%", objectFit: "cover", transform: mediaTransform(p, motion), filter: "saturate(.9) contrast(1.05)"}}
      />
    </MediaChrome>
  );
};

/** Real B-roll, looped deterministically when shorter than the narration. */
export const FootageScene: React.FC<MediaBase & {mediaDurationSeconds?: number}> = ({
  dur,
  src,
  motion = "push-in",
  mediaDurationSeconds = 8,
  ...rest
}) => {
  const {p} = useP(dur);
  const {fps} = useVideoConfig();
  const loopFrames = Math.max(1, Math.round(mediaDurationSeconds * fps));
  return (
    <MediaChrome dur={dur} src={src} motion={motion} {...rest}>
      <Loop durationInFrames={loopFrames}>
        <OffthreadVideo
          src={staticFile(src)}
          muted
          style={{width: "100%", height: "100%", objectFit: "cover", transform: mediaTransform(p, motion), filter: "saturate(.88) contrast(1.06)"}}
        />
      </Loop>
    </MediaChrome>
  );
};

// --- FigureScene: a real figure from the user's document ------------------- //

type FigureCallout = { label: string; region?: string; box?: [number, number, number, number] };
type Cam = { s: number; x: number; y: number };

const clampN = (v: number, lo: number, hi: number): number => Math.max(lo, Math.min(hi, v));
const lerpN = (a: number, b: number, t: number): number => a + (b - a) * t;

/** Drop a leading "Fig. 2 —" from the caption: the credit line under the
 * figure already reads "Figure 2 · <document>". */
const stripFigureLabel = (caption: string, label?: string): string => {
  const num = (label ?? "").replace(/^\D+/, "").trim();
  if (!num) return caption;
  const escaped = num.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const out = caption.replace(new RegExp(`^\\s*(fig(ure)?\\.?|figura|abbildung)\\s*${escaped}(?![0-9a-z])\\s*[.:·—–-]*\\s*`, "i"), "");
  return out.trim() ? out.charAt(0).toUpperCase() + out.slice(1) : caption;
};

/**
 * A figure cropped from the uploaded document, always shown whole (contain,
 * never cover) on a paper-white card, with numbered callouts revealed on their
 * narration cues. A callout carrying a `box` (normalised [x, y, w, h], set by
 * the worker from the vision pass) zooms the camera onto that region and
 * spotlights it; the camera returns to the whole figure after the last one.
 * Callouts without a box are only listed beside the figure.
 */
export const FigureScene: React.FC<
  Base & { src: string; aspect?: number; callouts?: FigureCallout[]; credit?: string; figureLabel?: string }
> = ({ dur, accent, title, caption: rawCaption, cues, src, aspect = 1.4, callouts = [], credit, figureLabel }) => {
  const { p } = useP(dur);
  const ac = accent ?? colors.user;
  const caption = rawCaption ? stripFigureLabel(rawCaption, figureLabel) : rawCaption;
  const items = callouts.filter((c) => c && c.label).slice(0, 5);
  const n = items.length;
  const starts = items.map((_, i) => cueOr(cues, i, 0.16 + (0.62 * i) / Math.max(1, n)));
  const wide = aspect >= 1.9;

  // Stage: below the title bar, above the caption line. The figure and its
  // callout list are laid out as one group centred in the stage: list on the
  // right for upright figures, a row of chips below for wide ones.
  const top = 150;
  const bottom = stageBottom(caption);
  const left = 90;
  const right = WIDTH - 90;
  const creditH = credit ? 38 : 0;
  const pad = 22;
  const gap = 64;
  const listW = 560;
  const layout = n === 0 ? "alone" : wide ? "stacked" : "side";
  const labels = items.map((c) => c.label);
  // Stacked: ONE row of equal chips (never wraps onto the caption), every
  // label fitted to its chip on <= 2 lines; the row's height is reserved.
  const chipGap = 16;
  const chipW = Math.min(440, (right - left - (n - 1) * chipGap) / Math.max(1, n));
  const chipBadge = 38;
  const chipFit = fitTogether(labels, { width: chipW - 32 - chipBadge - 12, maxLines: 2, max: 28, min: 19 });
  const rowH = Math.max(chipBadge, chipFit.lines * chipFit.fontSize * 1.18) + 24;
  // Side: a column of callouts beside the figure, labels on <= 2 lines.
  const listFit = fitTogether(labels, { width: listW - 40 - 44 - 18, maxLines: 2, max: 32, min: 24 });
  const availW = (layout === "side" ? right - left - listW - gap : right - left) - 2 * pad;
  const availH = bottom - top - 2 * pad - creditH - (layout === "stacked" ? rowH + 24 : 0);
  let imgW = availW;
  let imgH = availW / aspect;
  if (imgH > availH) {
    imgH = availH;
    imgW = availH * aspect;
  }
  const cardW = imgW + 2 * pad;
  const cardH = imgH + 2 * pad;
  const groupW = layout === "side" ? cardW + gap + listW : cardW;
  const groupH = cardH + creditH + (layout === "stacked" ? 24 + rowH : 0);
  const cardX = (WIDTH - groupW) / 2;
  const cardY = top + (bottom - top - groupH) / 2;

  // Camera: keyframes at each callout cue, eased over ~0.8 s.
  const overview: Cam = { s: 1, x: 0, y: 0 };
  const focusOn = ([bx, by, bw, bh]: [number, number, number, number]): Cam => {
    const s = clampN(Math.min(0.78 / Math.max(bw, 0.01), 0.78 / Math.max(bh, 0.01)), 1, 2.4);
    const cx = (bx + bw / 2) * imgW;
    const cy = (by + bh / 2) * imgH;
    return {
      s,
      x: clampN(imgW / 2 - cx * s, imgW - imgW * s, 0),
      y: clampN(imgH / 2 - cy * s, imgH - imgH * s, 0),
    };
  };
  const half = clampN(12 / dur, 0.015, 0.05);
  const anyBox = items.some((c) => c.box);
  const returnAt = anyBox ? Math.min(0.94, Math.max((starts[n - 1] ?? 0) + 0.16, 0.84)) : 2;
  const keys = items.map((c, i) => ({ at: starts[i], cam: c.box ? focusOn(c.box) : overview }));
  if (anyBox) keys.push({ at: returnAt, cam: overview });
  let cam = overview;
  for (const k of keys) {
    const a = beat(p, k.at - half, k.at + half);
    cam = { s: lerpN(cam.s, k.cam.s, a), x: lerpN(cam.x, k.cam.x, a), y: lerpN(cam.y, k.cam.y, a) };
  }
  const activeWeight = (i: number): number => {
    const end = i + 1 < n ? starts[i + 1] : returnAt;
    return beat(p, starts[i] - half, starts[i] + half) * (1 - beat(p, end - half, end + half));
  };
  const summary = anyBox ? beat(p, returnAt, returnAt + 2 * half) : 0;

  const enter = appear(p, 0, 0.06);
  // A slow push-in keeps the frame alive between callouts (no frozen stretch).
  const drift = 1 + 0.018 * p;

  const badge = (i: number, size: number, opacity: number): React.ReactNode => (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        background: ac,
        color: "#FFFFFF",
        fontFamily: fonts.sans,
        fontWeight: 800,
        fontSize: size * 0.55,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        boxShadow: "0 4px 14px rgba(0,0,0,.35)",
        opacity,
        flexShrink: 0,
      }}
    >
      {i + 1}
    </div>
  );

  return (
    <Shell dur={dur} accent={ac} title={title} caption={caption}>
      <div
        style={{
          position: "absolute",
          left: cardX,
          top: cardY,
          width: cardW,
          height: cardH,
          padding: pad,
          boxSizing: "border-box",
          background: "#FFFFFF",
          borderRadius: 16,
          boxShadow: "0 28px 70px rgba(0,0,0,.5)",
          opacity: enter,
          transform: `translateY(${(1 - enter) * 24}px) scale(${drift})`,
        }}
      >
        <div style={{ position: "relative", width: imgW, height: imgH, overflow: "hidden", borderRadius: 4 }}>
          <div
            style={{
              position: "absolute",
              left: 0,
              top: 0,
              width: imgW,
              height: imgH,
              transformOrigin: "0 0",
              transform: `translate(${cam.x}px, ${cam.y}px) scale(${cam.s})`,
            }}
          >
            <Img src={staticFile(src)} style={{ width: imgW, height: imgH, objectFit: "contain", display: "block" }} />
            {items.map((c, i) => {
              if (!c.box) return null;
              const [bx, by, bw, bh] = c.box;
              const w = activeWeight(i);
              const shown = Math.max(w, summary * 0.9);
              if (shown <= 0.001) return null;
              return (
                <div
                  key={i}
                  style={{
                    position: "absolute",
                    left: bx * imgW,
                    top: by * imgH,
                    width: bw * imgW,
                    height: bh * imgH,
                    border: `${4 / cam.s}px ${w > summary ? "solid" : "dashed"} ${ac}`,
                    borderRadius: 8 / cam.s,
                    // Spotlight: dim everything outside the active region.
                    boxShadow: w > 0.001 ? `0 0 0 4000px rgba(8,11,17,${0.42 * w})` : undefined,
                    opacity: shown,
                  }}
                >
                  {/* Badge on the region's corner, kept inside the figure. */}
                  <div
                    style={{
                      position: "absolute",
                      left: Math.max(-22 / cam.s, -bx * imgW),
                      top: Math.max(-22 / cam.s, -by * imgH),
                    }}
                  >
                    {badge(i, 44 / cam.s, 1)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
      {credit ? (
        <div
          style={{
            position: "absolute",
            left: cardX,
            top: cardY + cardH + 12,
            width: cardW,
            textAlign: "right",
            color: colors.muted,
            fontFamily: fonts.sans,
            fontSize: 20,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            opacity: enter,
          }}
        >
          {credit}
        </div>
      ) : null}
      {n > 0 ? (
        <div
          style={{
            position: "absolute",
            ...(layout === "stacked"
              ? { left, top: cardY + cardH + creditH + 24, width: right - left, height: rowH, flexDirection: "row" as const, justifyContent: "center", gap: chipGap }
              : { left: cardX + cardW + gap, top, width: listW, height: bottom - top, flexDirection: "column" as const, justifyContent: "center", gap: 22 }),
            display: "flex",
          }}
        >
          {items.map((c, i) => {
            const shown = appear(p, starts[i] - half, starts[i] + half);
            const active = activeWeight(i);
            const current = anyBox ? Math.max(active, summary) : i === n - 1 || p < (starts[i + 1] ?? 2) ? 1 : 0;
            return (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: layout === "stacked" ? 12 : 18,
                  ...(layout === "stacked" ? { width: chipW, height: rowH, padding: "0 16px" } : { padding: "14px 20px" }),
                  boxSizing: "border-box",
                  borderRadius: 14,
                  background: alpha(colors.panel, 0.85),
                  border: `2px solid ${active > 0.5 ? ac : colors.edge}`,
                  opacity: shown * (0.5 + 0.5 * current),
                  transform: layout === "stacked" ? `translateY(${(1 - shown) * 18}px)` : `translateX(${(1 - shown) * 28}px)`,
                }}
              >
                {badge(i, layout === "stacked" ? chipBadge : 44, 1)}
                <div
                  style={{
                    minWidth: 0,
                    color: colors.text,
                    fontFamily: fonts.sans,
                    fontSize: layout === "stacked" ? chipFit.fontSize : listFit.fontSize,
                    fontWeight: 600,
                    lineHeight: 1.18,
                    textWrap: "balance",
                    overflowWrap: "anywhere",
                  }}
                >
                  {c.label}
                </div>
              </div>
            );
          })}
        </div>
      ) : null}
    </Shell>
  );
};

/** A full-screen headline quotation revealed word-by-word, optional attribution. */
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
            opacity: appear(p, 0.04, 0.12) * 0.45,
            fontFamily: fonts.sans,
          }}
        >
          {"“"}
        </div>
        <TextReveal text={quote} fontSize={size} color={colors.text} delay={cQuote * dur} staggerDelay={4} />
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
            {"— "}
            {author}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

// --- SplitFocusScene: two live panels with bounded "kinds" ---------------- //
type SplitPanel =
  | { kind: "code"; code: string; lang?: string; codeTitle?: string }
  | { kind: "plot"; points: [number, number][]; xRange: [number, number]; yRange?: [number, number]; xLabel?: string; yLabel?: string }
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

const SplitPanelView: React.FC<{ panel: SplitPanel; p: number; start: number; accent: string }> = ({ panel, p, start, accent }) => {
  const reveal = appear(p, start, start + 0.12);
  const wrap = (children: React.ReactNode) => (
    <div
      style={{
        opacity: reveal,
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "0 5%",
        boxSizing: "border-box",
      }}
    >
      {children}
    </div>
  );
  if (panel.kind === "code") {
    return wrap(<CodeBlock code={panel.code} lang={panel.lang ?? "python"} fontSize={26} startAt={start} title={panel.codeTitle} accent={accent} />);
  }
  if (panel.kind === "terminal") {
    const text = `$ ${panel.command}${panel.output ? "\n" + panel.output : ""}`;
    return wrap(
      <pre
        style={{
          fontFamily: fonts.mono,
          fontSize: 26,
          color: colors.text,
          background: "#101722",
          border: `2px solid ${accent}`,
          borderRadius: 16,
          padding: 28,
          margin: 0,
          maxWidth: "100%",
          whiteSpace: "pre-wrap",
          textAlign: "left",
        }}
      >
        {text}
      </pre>,
    );
  }
  if (panel.kind === "formula") {
    return wrap(
      <div style={{ display: "flex", flexDirection: "column", gap: 28, alignItems: "center" }}>
        {panel.formulas.map((tex, i) => (
          <MathFormula key={i} tex={tex} display fontSize={48} color={colors.text} delay={start + i * 0.12} />
        ))}
      </div>,
    );
  }
  if (panel.kind === "bullets") {
    return wrap(
      <div style={{ display: "flex", flexDirection: "column", gap: 22, alignItems: "flex-start" }}>
        {panel.heading ? (
          <div style={{ fontSize: 36, fontWeight: 700, color: accent, fontFamily: fonts.sans, marginBottom: 8 }}>{panel.heading}</div>
        ) : null}
        {panel.bullets.map((b, i) => (
          <div
            key={i}
            style={{ fontSize: 32, color: colors.text, fontFamily: fonts.sans, opacity: appear(p, start + 0.1 + i * 0.1, start + 0.2 + i * 0.1) }}
          >
            {"• "}
            {b}
          </div>
        ))}
      </div>,
    );
  }
  return wrap(
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
    />,
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
      <div style={{ position: "absolute", left: 0, top: 200, width: WIDTH, height: 720, display: "flex" }}>
        <div style={{ width: WIDTH / 2, height: "100%", position: "relative" }}>
          <SplitPanelView panel={left} p={p} start={cLeft} accent={ac} />
        </div>
        <div style={{ width: WIDTH / 2, height: "100%", position: "relative" }}>
          <SplitPanelView panel={right} p={p} start={cRight} accent={colors.success} />
        </div>
      </div>
      <div style={{ position: "absolute", left: WIDTH / 2 - 1, top: 210, width: 2, height: 700, background: colors.edge, opacity: 0.5 }} />
    </Shell>
  );
};

// --- ZoomNarrativeScene: a camera that pans/zooms across a canvas ---------- //
type CanvasItem = { id: string; label: string; x: number; y: number; sub?: string; detail?: string };

/** Camera zooms/pans across a virtual canvas, focusing each path stop in turn. */
export const ZoomNarrativeScene: React.FC<Base & { canvas: CanvasItem[]; path: string[] }> = ({ dur, accent, title, cues, canvas, path }) => {
  const { p } = useP(dur);
  const ac = accent ?? colors.user;
  const byId: Record<string, CanvasItem> = Object.fromEntries(canvas.map((c) => [c.id, c]));
  const stops = path.map((id) => byId[id]).filter(Boolean) as CanvasItem[];
  if (stops.length === 0) {
    return (
      <AbsoluteFill>
        <AmbientBackground accent={ac} />
      </AbsoluteFill>
    );
  }
  // Strictly-increasing camera keyframes: one per stop (at its cue), then an
  // overview keyframe (scale 1, centred) at the end.
  const times: number[] = [];
  let prev = 0;
  stops.forEach((_, i) => {
    const raw = cueOr(cues, i, 0.12 + (i * (0.82 - 0.12)) / Math.max(1, stops.length));
    const v = Math.max(prev + 0.001, raw);
    times.push(v);
    prev = v;
  });
  const overview = Math.max(prev + 0.02, 0.92);
  times.push(overview);
  const ZOOM = 1.9;
  const targetsX = stops.map((s) => s.x).concat([0]);
  const targetsY = stops.map((s) => s.y).concat([0]);
  const scales = stops.map(() => ZOOM).concat([1]);
  const clampOpts = { extrapolateLeft: "clamp" as const, extrapolateRight: "clamp" as const };
  const camX = interpolate(p, times, targetsX, clampOpts);
  const camY = interpolate(p, times, targetsY, clampOpts);
  const scale = interpolate(p, times, scales, clampOpts);
  // Move so the focused world point lands at screen centre, scaled about centre.
  const tx = -camX * mu(1) * scale;
  const ty = camY * mu(1) * scale;
  return (
    <AbsoluteFill>
      <AmbientBackground accent={ac} />
      {title ? <TitleBar label={title} opacity={appear(p, 0, 0.08)} /> : null}
      <AbsoluteFill style={{ transform: `translate(${tx}px, ${ty}px) scale(${scale})`, transformOrigin: "center center" }}>
        {canvas.map((item) => {
          const stopIdx = path.indexOf(item.id);
          const focusT = times[stopIdx >= 0 ? stopIdx : 0];
          const reveal = appear(p, focusT, focusT + 0.1);
          return (
            <div key={item.id} style={{ opacity: 0.32 + 0.68 * reveal }}>
              <Card x={item.x} y={item.y} w={2.4} h={1.2} accent={ac} glow={reveal} fontPx={28}>
                {item.sub ? (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
                    <FitText text={item.label} width={mu(2.4) - 28} maxLines={2} max={26} min={16} lineHeight={1.12} />
                    <FitText text={item.sub} width={mu(2.4) - 28} maxLines={1} max={18} min={13} weight={400} color={colors.muted} />
                  </div>
                ) : (
                  item.label
                )}
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

// --- NetworkMapScene: an animated node-link graph -------------------------- //
type NetNode = { id: string; label: string; x: number; y: number; group?: string };
type NetLink = { a: string; b: string; label?: string };

const NET_GROUP_COLORS = [colors.user, colors.success, colors.purple, colors.kernel];

/** Animated node-link graph; nodes light up on cue, edges draw after both ends. */
export const NetworkMapScene: React.FC<Base & { nodes: NetNode[]; links: NetLink[] }> = ({ dur, accent, title, caption, cues, nodes, links }) => {
  const { p } = useP(dur);
  const ac = accent ?? colors.user;
  const indexOf: Record<string, number> = Object.fromEntries(nodes.map((n, i) => [n.id, i]));
  const byId: Record<string, NetNode> = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const groups = Array.from(new Set(nodes.map((n) => n.group ?? "_")));
  const colorFor = (n: NetNode) => NET_GROUP_COLORS[groups.indexOf(n.group ?? "_") % NET_GROUP_COLORS.length] ?? ac;
  const nodeCue = (i: number) => cueOr(cues, i, 0.12 + (i * 0.6) / Math.max(1, nodes.length));
  return (
    <Shell dur={dur} accent={ac} title={title} caption={caption}>
      {links.map((lk, i) => {
        const a = byId[lk.a];
        const b = byId[lk.b];
        if (!a || !b) return null;
        const start = Math.max(nodeCue(indexOf[lk.a] ?? 0), nodeCue(indexOf[lk.b] ?? 0));
        const progress = beat(p, start, start + 0.16, "linear");
        return <Arrow key={`l${i}`} from={[a.x, a.y]} to={[b.x, b.y]} color={colors.edge} width={2.5} progress={progress} opacity={0.7} />;
      })}
      {nodes.map((n, i) => {
        const reveal = appear(p, nodeCue(i), nodeCue(i) + 0.1);
        return (
          <div key={n.id} style={{ opacity: reveal }}>
            <Card x={n.x} y={n.y} w={1.9} h={0.82} accent={colorFor(n)} glow={reveal * 0.8} fontPx={22}>
              {n.label}
            </Card>
          </div>
        );
      })}
    </Shell>
  );
};
