import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { AmbientBackground } from "../../catalog/AmbientBackground";
import { MathFormula } from "../../catalog/MathFormula";
import { CodeBlock } from "../../catalog/CodeBlock";
import { Plot } from "../../catalog/Plot";
import { TextReveal, BlurReveal } from "../../catalog/text";
import { Arrow, Caption, Card, TitleBar } from "../../components/primitives";
import { colors, mx, my } from "../../style/tokens";

/**
 * Data-driven STEM scene templates. Each reads plain props (no code) so a
 * blueprint produced by the LLM — or a deterministic builder — can render a real
 * video by *composing the tested library*. `dur` is the scene's length in
 * frames (injected by MainComposition); beats are driven off p = frame / dur.
 */

type Base = { dur: number; accent?: string; title?: string; caption?: string };

const useP = (dur: number) => {
  const frame = useCurrentFrame();
  return { frame, p: frame / dur };
};
const fadeTail = (p: number) => interpolate(p, [0.95, 1], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
const inOp = (p: number, a: number, b: number) =>
  interpolate(p, [a, b], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

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
    <AbsoluteFill style={{ opacity: fadeTail(p) }}>
      <AmbientBackground accent={ac} />
      {title ? <TitleBar label={title} opacity={inOp(p, 0, 0.08)} /> : null}
      {children}
      {caption ? (
        <Caption x={0} y={-3.05} label={caption} color={colors.muted} size={28} opacity={inOp(p, 0.55, 0.68)} width={13} />
      ) : null}
    </AbsoluteFill>
  );
};

/** Big title + subtitle. Use to open a video or a section. */
export const TitleScene: React.FC<Base & { subtitle?: string }> = ({ dur, accent, title = "", subtitle }) => {
  const { frame, p } = useP(dur);
  return (
    <AbsoluteFill style={{ opacity: fadeTail(p), alignItems: "center", justifyContent: "center" }}>
      <AmbientBackground accent={accent ?? colors.purple} />
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 30 }}>
        <TextReveal text={title} fontSize={84} color={colors.text} staggerDelay={4} />
        {subtitle ? (
          <div style={{ opacity: inOp(p, 0.25, 0.4) }}>
            <BlurReveal text={subtitle} fontSize={40} color={colors.muted} delay={Math.round(0.25 * dur)} />
          </div>
        ) : null}
      </div>
      <div style={{ position: "absolute", bottom: 120, width: 280, height: 4, borderRadius: 2, background: accent ?? colors.purple, opacity: interpolate(frame, [0, 20], [0, 0.8], { extrapolateRight: "clamp" }) }} />
    </AbsoluteFill>
  );
};

/** Title + staggered bullet points. Use for definitions, properties, steps. */
export const BulletScene: React.FC<Base & { bullets: string[] }> = ({ dur, accent, title, caption, bullets }) => {
  const { p } = useP(dur);
  const ac = accent ?? colors.user;
  return (
    <Shell dur={dur} accent={ac} title={title} caption={caption}>
      <div style={{ position: "absolute", left: mx(-5.2), top: my(1.6), display: "flex", flexDirection: "column", gap: 34, width: mx(5.2) - mx(-5.2) }}>
        {bullets.slice(0, 6).map((b, i) => {
          const start = 0.12 + i * 0.12;
          const op = inOp(p, start, start + 0.1);
          return (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 22, opacity: op, transform: `translateX(${interpolate(op, [0, 1], [-30, 0])}px)` }}>
              <div style={{ width: 16, height: 16, borderRadius: 4, background: ac, flexShrink: 0, transform: "rotate(45deg)" }} />
              <span style={{ color: colors.text, fontFamily: "Inter, sans-serif", fontSize: 38, fontWeight: 500 }}>{b}</span>
            </div>
          );
        })}
      </div>
    </Shell>
  );
};

/** Title + up to 3 LaTeX formulas stepping in. Use for math/derivations. */
export const FormulaScene: React.FC<Base & { formulas: string[] }> = ({ dur, accent, title, caption, formulas }) => {
  const { p } = useP(dur);
  return (
    <Shell dur={dur} accent={accent ?? colors.kernel} title={title} caption={caption} accentDefault={colors.kernel}>
      <div style={{ position: "absolute", left: 0, width: 1920, top: my(2.3), height: my(-2.5) - my(2.3), display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 40 }}>
        {formulas.slice(0, 3).map((tex, i) => {
          const start = 0.12 + i * 0.2;
          return (
            <div key={i} style={{ opacity: inOp(p, start, start + 0.12) }}>
              <MathFormula tex={tex} fontSize={i === 0 ? 54 : 44} color={i === formulas.length - 1 ? (accent ?? colors.kernel) : colors.text} delay={Math.round(start * dur)} />
            </div>
          );
        })}
      </div>
    </Shell>
  );
};

/** Title + syntax-highlighted code revealed line by line. Use for CS/algorithms. */
export const CodeScene: React.FC<Base & { code: string; lang?: string; codeTitle?: string }> = ({ dur, accent, title, caption, code, lang = "python", codeTitle }) => {
  return (
    <Shell dur={dur} accent={accent ?? colors.purple} title={title} caption={caption} accentDefault={colors.purple}>
      <div style={{ position: "absolute", left: 0, width: 1920, top: my(1.4), display: "flex", justifyContent: "center" }}>
        <CodeBlock code={code} lang={lang} title={codeTitle} startAt={Math.round(0.12 * dur)} lineReveal={Math.max(4, Math.round(0.05 * dur))} fontSize={30} accent={accent ?? colors.purple} />
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
> = ({ dur, accent, title, caption, points, xRange, yRange, xLabel, yLabel, sweep = false, area = false, color }) => {
  const { p } = useP(dur);
  const draw = interpolate(p, [0.12, 0.45], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
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
  const sweepX = sweep ? interpolate(p, [0.5, 0.9], [xRange[0], xRange[1]], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : null;
  const areaTo = area ? interpolate(p, [0.5, 0.85], [xRange[0], xRange[1]], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : null;
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
    nodes: { id: string; label: string; x: number; y: number; color?: string }[];
    edges: { from: string; to: string; color?: string; label?: string }[];
  }
> = ({ dur, accent, title, caption, nodes, edges }) => {
  const { p } = useP(dur);
  const pos: Record<string, { x: number; y: number }> = {};
  nodes.forEach((n) => (pos[n.id] = { x: n.x, y: n.y }));
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <Shell dur={dur} accent={accent ?? colors.user} title={title} caption={caption}>
      {edges.map((e, i) => {
        const a = pos[e.from];
        const b = pos[e.to];
        if (!a || !b) return null;
        const start = 0.3 + i * 0.06;
        const prog = interpolate(p, [start, start + 0.1], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        return <Arrow key={i} from={[a.x, a.y]} to={[b.x, b.y]} color={e.color ?? colors.muted} width={3} progress={prog} />;
      })}
      {nodes.map((n, i) => {
        const s = spring({ frame: frame - Math.round((0.12 + i * 0.08) * dur), fps, config: { damping: 14, stiffness: 120 } });
        return (
          <div key={n.id} style={{ transform: `scale(${s})`, transformOrigin: `${mx(n.x)}px ${my(n.y)}px` }}>
            <Card x={n.x} y={n.y} w={2.2} h={1.0} accent={n.color ?? colors.user} opacity={interpolate(p, [0.1 + i * 0.08, 0.18 + i * 0.08], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })} fontPx={26}>
              {n.label}
            </Card>
          </div>
        );
      })}
    </Shell>
  );
};
