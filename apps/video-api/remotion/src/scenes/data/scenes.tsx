import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { AmbientBackground } from "../../catalog/AmbientBackground";
import { MathFormula } from "../../catalog/MathFormula";
import { CodeBlock } from "../../catalog/CodeBlock";
import { Plot } from "../../catalog/Plot";
import { TextReveal, BlurReveal } from "../../catalog/text";
import { MemoryGrid, type MemoryCell } from "../../catalog/MemoryGrid";
import { FlowToken } from "../../catalog/FlowToken";
import { BarChart, type Bar } from "../../catalog/BarChart";
import { Counter } from "../../catalog/Counter";
import { Icon } from "../../catalog/Icon";
import { Arrow, Caption, Card, Terminal, TitleBar, Zone } from "../../components/primitives";
import { colors, fonts, mu, mx, my, WIDTH } from "../../style/tokens";
import { appear, cueOr, dimAt, lastCue } from "../../style/anim";

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
  return (
    <Shell dur={dur} accent={ac} title={title} caption={caption}>
      <div style={{ position: "absolute", left: mx(-5.2), top: my(1.6), display: "flex", flexDirection: "column", gap: 34, width: mx(5.2) - mx(-5.2) }}>
        {bullets.slice(0, 6).map((b, i, arr) => {
          const start = cueOr(cues, i, 0.12 + i * 0.12);
          const enter = appear(p, start, start + 0.1);
          // Focus the bullet currently being spoken: once the NEXT bullet
          // appears, gently dim this one so attention follows the narration
          // while the whole list stays readable. The last bullet stays bright.
          const isLast = i === arr.length - 1;
          const focus = isLast ? 1 : dimAt(p, cueOr(cues, i + 1, start + 0.12), 0.6);
          const icon = icons?.[i];
          return (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 22, opacity: enter * focus, transform: `translateX(${interpolate(enter, [0, 1], [-30, 0])}px)` }}>
              {icon ? (
                <Icon name={icon} size={34} color={ac} />
              ) : (
                <div style={{ width: 16, height: 16, borderRadius: 4, background: ac, flexShrink: 0, transform: "rotate(45deg)" }} />
              )}
              <span style={{ color: colors.text, fontFamily: "Inter, sans-serif", fontSize: 38, fontWeight: 500 }}>{b}</span>
            </div>
          );
        })}
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

/** Axes + a curve from sampled points, with an optional sweeping marker + area. */
export const PlotScene: React.FC<
  Base & {
    points: [number, number][];
    xRange: [number, number];
    yRange: [number, number];
    xLabel?: string;
    yLabel?: string;
    sweep?: boolean;
    area?: boolean;
    color?: string;
  }
> = ({ dur, accent, title, caption, cues, points, xRange, yRange, xLabel, yLabel, sweep = false, area = false, color }) => {
  const { p } = useP(dur);
  // cues[0] = curve drawn while spoken; cues[1] = sweep/area while spoken.
  const c0 = cueOr(cues, 0, 0.12);
  const c1 = Math.max(c0 + 0.1, cueOr(cues, 1, 0.5));
  const draw = interpolate(p, [c0, c0 + 0.33], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  // build an interpolating fn from points
  const fn = (x: number) => {
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
  const sweepX = sweep ? interpolate(p, [c1, Math.min(0.95, c1 + 0.4)], [xRange[0], xRange[1]], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : null;
  const areaTo = area ? interpolate(p, [c1, Math.min(0.92, c1 + 0.35)], [xRange[0], xRange[1]], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : null;
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
          xLabel={xLabel ?? "x"}
          yLabel={yLabel ?? "y"}
        />
      </div>
    </Shell>
  );
};

/** General node-edge diagram (systems, processes, relationships). x,y in Manim units. */
export const DiagramScene: React.FC<
  Base & {
    nodes: { id: string; label: string; x: number; y: number; color?: string; icon?: string }[];
    edges: { from: string; to: string; color?: string; label?: string }[];
  }
> = ({ dur, accent, title, caption, cues, nodes, edges }) => {
  const { p } = useP(dur);
  const pos: Record<string, { x: number; y: number }> = {};
  const nodeStart: Record<string, number> = {};
  nodes.forEach((n, i) => {
    pos[n.id] = { x: n.x, y: n.y };
    nodeStart[n.id] = cueOr(cues, i, 0.12 + i * 0.08);
  });
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <Shell dur={dur} accent={accent ?? colors.user} title={title} caption={caption}>
      {edges.map((e, i) => {
        const a = pos[e.from];
        const b = pos[e.to];
        if (!a || !b) return null;
        // An edge never draws toward a node that hasn't appeared yet (cues can
        // reorder node reveals relative to the default grid).
        const start = Math.max(0.3 + i * 0.06, (nodeStart[e.to] ?? 0) + 0.04);
        const prog = interpolate(p, [start, start + 0.1], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        return <Arrow key={i} from={[a.x, a.y]} to={[b.x, b.y]} color={e.color ?? colors.muted} width={3} progress={prog} />;
      })}
      {nodes.map((n) => {
        const start = nodeStart[n.id];
        const s = spring({ frame: frame - Math.round(start * dur), fps, config: { damping: 14, stiffness: 120 } });
        return (
          <div key={n.id} style={{ transform: `scale(${s})`, transformOrigin: `${mx(n.x)}px ${my(n.y)}px` }}>
            <Card x={n.x} y={n.y} w={2.2} h={1.0} accent={n.color ?? colors.user} opacity={interpolate(p, [start, start + 0.08], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })} fontPx={26}>
              {n.icon ? (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
                  <Icon name={n.icon} size={26} color={n.color ?? colors.user} />
                  {n.label}
                </span>
              ) : (
                n.label
              )}
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
  // Cue order matches the blueprint contract: all left items, then all right
  // items. Each column's zone/header leads its first cued item slightly.
  const column = (side: { label: string; items: string[] }, cx: number, color: string, base: number, offset: number) => {
    const firstCue = cues?.[offset];
    const zoneStart = firstCue != null ? Math.max(0.03, firstCue - 0.08) : base;
    return (
      <>
        <Zone x={cx} y={-0.45} w={5.7} h={4.1} color={color} fill={`${color}12`} opacity={appear(p, zoneStart, zoneStart + 0.1)} />
        {/* Header centered over THIS column (not the full screen). */}
        <div style={{ position: "absolute", left: mx(cx) - mu(2.85), top: my(2.05), width: mu(5.7), textAlign: "center", opacity: appear(p, zoneStart, zoneStart + 0.1) }}>
          <span style={{ color, fontFamily: fonts.sans, fontSize: 31, fontWeight: 700 }}>{side.label}</span>
        </div>
        <div style={{ position: "absolute", left: mx(cx) - mu(2.4), top: my(1.15), width: mu(4.8), display: "flex", flexDirection: "column", gap: 24 }}>
          {(side.items ?? []).slice(0, 5).map((it, i) => {
            const start = cueOr(cues, offset + i, base + 0.14 + i * 0.1);
            const op = appear(p, start, start + 0.1);
            return (
              <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 14, opacity: op }}>
                <div style={{ width: 12, height: 12, marginTop: 9, borderRadius: 3, background: color, flexShrink: 0, transform: "rotate(45deg)" }} />
                <span style={{ color: colors.text, fontFamily: fonts.sans, fontSize: 29, fontWeight: 500, lineHeight: 1.25 }}>{it}</span>
              </div>
            );
          })}
        </div>
      </>
    );
  };
  return (
    <Shell dur={dur} accent={accent ?? colors.user} title={title} caption={caption}>
      {column(left, -3.35, accent ?? colors.user, 0.1, 0)}
      {column(right, 3.35, colors.kernel, 0.22, (left.items ?? []).slice(0, 5).length)}
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
  return (
    <Shell dur={dur} accent={accent ?? colors.user} title={title} caption={caption}>
      {items.map((layer, i) => {
        const cy = top - bandH / 2 - i * (bandH + gap);
        const start = cueOr(cues, i, 0.12 + i * 0.12);
        const op = appear(p, start, start + 0.12);
        const color = layer.color ?? LAYER_COLORS[i % LAYER_COLORS.length];
        return (
          <React.Fragment key={i}>
            <Zone x={0} y={cy} w={9.2} h={bandH} color={color} fill={`${color}16`} opacity={op} />
            <div style={{ position: "absolute", left: 0, width: WIDTH, top: my(cy) - 24, textAlign: "center", opacity: op }}>
              <span style={{ color: colors.text, fontFamily: fonts.sans, fontSize: 34, fontWeight: 700 }}>{layer.label}</span>
              {layer.sub ? <span style={{ color: colors.muted, fontFamily: fonts.sans, fontSize: 24, marginLeft: 16 }}>{layer.sub}</span> : null}
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
            <div style={{ opacity: op * focus }}>
              <Card x={cx} y={0} w={1.5} h={1.0} accent={ac} fontPx={30}>{`${i + 1}`}</Card>
            </div>
            <div style={{ position: "absolute", left: mx(cx) - mu(1.5), top: my(-0.9), width: mu(3.0), textAlign: "center", opacity: op }}>
              <div style={{ color: colors.text, fontFamily: fonts.sans, fontSize: 26, fontWeight: 600, lineHeight: 1.2 }}>{step.label}</div>
              {step.sub ? <div style={{ color: colors.muted, fontFamily: fonts.sans, fontSize: 20 }}>{step.sub}</div> : null}
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
  return (
    <Shell dur={dur} accent={ac} title={title} caption={caption}>
      {items.slice(0, -1).map((_, i) => (
        <Arrow key={i} from={[xs[i], y]} to={[xs[i + 1], y]} color={colors.edge} width={3} progress={appear(p, 0.1, 0.25)} />
      ))}
      {items.map((st, i) => {
        const op = appear(p, 0.12 + i * 0.06, 0.22 + i * 0.06);
        return (
          <React.Fragment key={i}>
            <div style={{ opacity: op }}>
              <Card x={xs[i]} y={y} w={2.0} h={1.0} accent={ac} glow={i === active ? 0.85 : 0} fontPx={24}>
                {st.icon ? (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                    <Icon name={st.icon} size={24} color={ac} />
                    {st.label}
                  </span>
                ) : (
                  st.label
                )}
              </Card>
            </div>
            {st.sub ? <Caption x={xs[i]} y={y - 0.95} label={st.sub} color={colors.muted} size={20} width={2.6} opacity={op} /> : null}
          </React.Fragment>
        );
      })}
      {n > 1 ? <FlowToken from={[xs[seg], y + 0.85]} to={[xs[seg + 1], y + 0.85]} progress={segP} color={ac} opacity={appear(p, 0.2, 0.3)} /> : null}
    </Shell>
  );
};

/** Animated bar chart for quantities / benchmarks / comparisons. */
export const BarChartScene: React.FC<Base & { bars: Bar[] }> = ({ dur, accent, title, caption, cues, bars }) => {
  const { p } = useP(dur);
  const c0 = cueOr(cues, 0, 0.15);
  const cEnd = Math.max(c0 + 0.2, lastCue(cues, 0.6));
  return (
    <Shell dur={dur} accent={accent ?? colors.user} title={title} caption={caption}>
      <div style={{ position: "absolute", left: 0, width: WIDTH, top: my(1.9), display: "flex", justifyContent: "center" }}>
        <BarChart bars={bars} grow={appear(p, c0, cEnd)} />
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
