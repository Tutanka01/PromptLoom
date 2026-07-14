import React from "react";
import { alpha, colors, fonts } from "../style/tokens";

/**
 * 2D function/data plot — a universal STEM primitive (calculus, physics,
 * statistics, economics…). Pure SVG, deterministic.
 *
 * Single curve (legacy API, unchanged):
 *   <Plot fn={(x) => 0.25 * x * x} xRange={[-4, 4]} yRange={[0, 4]}
 *         drawProgress={p} tangentAt={x} pointAt={x} areaTo={x} />
 *
 * Several curves on the same axes (supply/demand, compared functions…):
 *   <Plot xRange={[0, 10]}
 *         series={[
 *           { fn: (q) => 10 - 0.8 * q, label: "Demande" },
 *           { fn: (q) => 1 + 0.7 * q, label: "Offre" },
 *         ]}
 *         markers={[{ x: 6, y: 5.2, label: "E", guides: true }]}
 *         xLabel="Quantité" yLabel="Prix" />
 *
 * Guarantees the hand-rolled charts never had: the plot area is CLIPPED (a
 * curve can never overflow the frame), axes carry numeric tick labels, the
 * y-range auto-fits the data when omitted, and the draw animation uses the
 * real path length.
 */

export type PlotSeries = {
  /** y = fn(x), sampled over xRange. Provide fn OR points. */
  fn?: (x: number) => number;
  /** Pre-sampled [x, y] pairs (must be sorted by x). */
  points?: readonly (readonly [number, number])[] | number[][];
  color?: string;
  /** Shown in the automatic legend (legend appears when any series has one). */
  label?: string;
  /** Dashed stroke (secondary/reference curves). */
  dash?: boolean;
  /** 0..1 — overrides the plot-level drawProgress for this series. */
  drawProgress?: number;
};

export type PlotMarker = {
  x: number;
  y: number;
  /** Short name rendered next to the point (e.g. "E" for equilibrium). */
  label?: string;
  color?: string;
  /** Dashed guide lines to both axes, with the x/y values at their feet. */
  guides?: boolean;
  /** 0..1 opacity gate so the marker can appear on its narration cue. */
  progress?: number;
};

const SERIES_COLORS = [colors.user, colors.danger, colors.success, colors.kernel, colors.purple];

/** "3", "0.5", "12.25" — fixed-point, no float noise, locale-independent. */
const fmt = (v: number): string => String(parseFloat(v.toFixed(2)));

function niceStep(range: number): number {
  const raw = range / 6;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10;
  return step * mag;
}

export const Plot: React.FC<{
  fn?: (x: number) => number;
  series?: PlotSeries[];
  xRange: [number, number];
  /** Omit to auto-fit the plotted values (recommended unless you need a fixed scale). */
  yRange?: [number, number];
  width?: number;
  height?: number;
  color?: string;
  drawProgress?: number; // 0..1, animates the curve(s) being drawn
  tangentAt?: number | null; // x value to draw a tangent line at (first fn series)
  pointAt?: number | null; // x value to mark a dot (first fn series)
  areaTo?: number | null; // shade area under the first curve up to this x
  markers?: PlotMarker[];
  xLabel?: string;
  yLabel?: string;
  showTicks?: boolean;
}> = ({
  fn,
  series,
  xRange,
  yRange,
  width = 760,
  height = 560,
  color = colors.user,
  drawProgress = 1,
  tangentAt = null,
  pointAt = null,
  areaTo = null,
  markers = [],
  xLabel = "x",
  yLabel = "y",
  showTicks = true,
}) => {
  const clipId = React.useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const padL = showTicks ? 84 : 48;
  const padR = 30;
  const padT = 30;
  const padB = showTicks ? 66 : 48;
  const [xMin, xMax] = xRange;

  const list: PlotSeries[] =
    series && series.length > 0 ? series : fn ? [{ fn, color, drawProgress }] : [];

  // Sample every series once (fn on a uniform grid, points passed through).
  const N = 240;
  const sampled: [number, number][][] = list.map((s) => {
    if (s.points && s.points.length > 0) {
      return (s.points as number[][])
        .filter((p) => Number.isFinite(p[0]) && Number.isFinite(p[1]))
        .map((p) => [p[0], p[1]] as [number, number]);
    }
    const f = s.fn;
    if (!f) return [];
    const pts: [number, number][] = [];
    for (let i = 0; i <= N; i++) {
      const x = xMin + ((xMax - xMin) * i) / N;
      const y = f(x);
      if (Number.isFinite(y)) pts.push([x, y]);
    }
    return pts;
  });

  // y-range: honour the prop, otherwise fit the data (plus markers) with headroom.
  let yMin: number;
  let yMax: number;
  if (yRange) {
    [yMin, yMax] = yRange;
  } else {
    const ys = sampled.flat().map(([, y]) => y).concat(markers.map((m) => m.y));
    let lo = ys.length ? Math.min(...ys) : 0;
    let hi = ys.length ? Math.max(...ys) : 1;
    if (hi - lo < 1e-9) {
      hi = lo + 1;
    }
    // A positive baseline close to 0 reads better anchored at 0.
    if (lo > 0 && lo < 0.35 * hi) lo = 0;
    const head = 0.08 * (hi - lo);
    yMin = lo === 0 ? 0 : lo - head;
    yMax = hi + head;
  }

  const sx = (x: number) => padL + ((x - xMin) / (xMax - xMin)) * (width - padL - padR);
  const sy = (y: number) => height - padB - ((y - yMin) / (yMax - yMin)) * (height - padT - padB);
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  // Gridlines + numeric tick labels at nice steps.
  const xStep = niceStep(xMax - xMin);
  const yStep = niceStep(yMax - yMin);
  const grid: React.ReactNode[] = [];
  const ticks: React.ReactNode[] = [];
  for (let x = Math.ceil(xMin / xStep) * xStep; x <= xMax + 1e-9; x += xStep) {
    grid.push(
      <line key={`gx${x}`} x1={sx(x)} y1={sy(yMin)} x2={sx(x)} y2={sy(yMax)} style={{ stroke: colors.edge }} strokeWidth={1} opacity={0.4} />,
    );
    if (showTicks && sx(x) > padL + 8) {
      ticks.push(
        <text key={`tx${x}`} x={sx(x)} y={height - padB + 32} textAnchor="middle" style={{ fill: colors.muted }} fontSize={20} fontFamily={fonts.sans}>
          {fmt(x)}
        </text>,
      );
    }
  }
  for (let y = Math.ceil(yMin / yStep) * yStep; y <= yMax + 1e-9; y += yStep) {
    grid.push(
      <line key={`gy${y}`} x1={sx(xMin)} y1={sy(y)} x2={sx(xMax)} y2={sy(y)} style={{ stroke: colors.edge }} strokeWidth={1} opacity={0.4} />,
    );
    if (showTicks && sy(y) < height - padB - 6) {
      ticks.push(
        <text key={`ty${y}`} x={padL - 14} y={sy(y) + 7} textAnchor="end" style={{ fill: colors.muted }} fontSize={20} fontFamily={fonts.sans}>
          {fmt(y)}
        </text>,
      );
    }
  }

  // Frame axes hug the plot area; a zero line is added when 0 is inside a range.
  const xAxisY = sy(Math.min(Math.max(0, yMin), yMax));
  const yAxisX = sx(Math.min(Math.max(0, xMin), xMax));

  // Per-series scaled path + its REAL length (so dash-draw animation is exact).
  const paths = sampled.map((pts) => {
    let d = "";
    let len = 0;
    let px = 0;
    let py = 0;
    pts.forEach(([x, y], i) => {
      const X = sx(x);
      const Y = sy(y);
      d += `${i === 0 ? "M" : "L"}${X.toFixed(1)},${Y.toFixed(1)} `;
      if (i > 0) len += Math.hypot(X - px, Y - py);
      px = X;
      py = Y;
    });
    return { d: d.trim(), len: Math.max(1, len) };
  });

  // Area under the FIRST curve, from xMin to areaTo (baseline clamped in-range).
  let areaPath: string | null = null;
  const firstFn = list.find((s) => s.fn)?.fn;
  if (areaTo != null && firstFn) {
    const baseY = sy(Math.min(Math.max(0, yMin), yMax));
    const ap: string[] = [`M${sx(xMin).toFixed(1)},${baseY.toFixed(1)}`];
    for (let i = 0; i <= N; i++) {
      const x = xMin + ((areaTo - xMin) * i) / N;
      const y = firstFn(x);
      if (Number.isFinite(y)) ap.push(`L${sx(x).toFixed(1)},${sy(y).toFixed(1)}`);
    }
    ap.push(`L${sx(areaTo).toFixed(1)},${baseY.toFixed(1)} Z`);
    areaPath = ap.join(" ");
  }

  // Tangent line on the first fn series.
  let tangent: React.ReactNode = null;
  if (tangentAt != null && firstFn) {
    const h = 1e-3;
    const slope = (firstFn(tangentAt + h) - firstFn(tangentAt - h)) / (2 * h);
    const y0 = firstFn(tangentAt);
    const tLine = (x: number) => y0 + slope * (x - tangentAt);
    tangent = (
      <line
        x1={sx(xMin)}
        y1={sy(tLine(xMin))}
        x2={sx(xMax)}
        y2={sy(tLine(xMax))}
        style={{ stroke: colors.kernel }}
        strokeWidth={3}
        strokeDasharray="8 6"
      />
    );
  }

  const legendEntries = list
    .map((s, i) => ({ label: s.label, color: s.color ?? SERIES_COLORS[i % SERIES_COLORS.length], dash: s.dash }))
    .filter((e): e is { label: string; color: string; dash: boolean | undefined } => Boolean(e.label));

  return (
    <svg width={width} height={height}>
      <defs>
        <clipPath id={clipId}>
          <rect x={padL} y={padT} width={plotW} height={plotH} />
        </clipPath>
      </defs>

      {grid}
      {ticks}

      {/* frame + zero axes */}
      <line x1={padL} y1={height - padB} x2={width - padR} y2={height - padB} style={{ stroke: colors.muted }} strokeWidth={2} />
      <line x1={padL} y1={padT} x2={padL} y2={height - padB} style={{ stroke: colors.muted }} strokeWidth={2} />
      {yMin < 0 && yMax > 0 && (
        <line x1={padL} y1={xAxisY} x2={width - padR} y2={xAxisY} style={{ stroke: colors.muted }} strokeWidth={1.5} opacity={0.8} />
      )}
      {xMin < 0 && xMax > 0 && (
        <line x1={yAxisX} y1={padT} x2={yAxisX} y2={height - padB} style={{ stroke: colors.muted }} strokeWidth={1.5} opacity={0.8} />
      )}
      <text x={width - padR} y={height - padB + (showTicks ? 60 : 32)} textAnchor="end" style={{ fill: colors.muted }} fontSize={22} fontFamily={fonts.sans} fontWeight={600}>
        {xLabel}
      </text>
      <text x={padL + 10} y={padT - 8} style={{ fill: colors.muted }} fontSize={22} fontFamily={fonts.sans} fontWeight={600}>
        {yLabel}
      </text>

      {/* everything data-driven is clipped: a curve can NEVER overflow the frame */}
      <g clipPath={`url(#${clipId})`}>
        {areaPath && <path d={areaPath} style={{ fill: alpha(color, 0.2) }} stroke="none" />}
        {paths.map((path, i) => {
          const s = list[i];
          const prog = Math.max(0, Math.min(1, s.drawProgress ?? drawProgress));
          // At progress 0 the rounded dash cap would still paint a dot at the
          // path's end — skip the not-yet-started curve entirely.
          if (prog < 0.005) return null;
          return (
            <path
              key={i}
              d={path.d}
              fill="none"
              style={{ stroke: s.color ?? SERIES_COLORS[i % SERIES_COLORS.length] }}
              strokeWidth={4}
              strokeLinecap="round"
              strokeDasharray={path.len}
              strokeDashoffset={path.len * (1 - prog)}
            />
          );
        })}
        {tangent}
        {markers.map((m, i) => {
          const op = Math.max(0, Math.min(1, m.progress ?? 1));
          if (op <= 0 || !m.guides) return null;
          const mc = m.color ?? colors.kernel;
          return (
            <g key={`g${i}`} opacity={op}>
              <line x1={padL} y1={sy(m.y)} x2={sx(m.x)} y2={sy(m.y)} style={{ stroke: mc }} strokeWidth={2} strokeDasharray="6 6" opacity={0.75} />
              <line x1={sx(m.x)} y1={height - padB} x2={sx(m.x)} y2={sy(m.y)} style={{ stroke: mc }} strokeWidth={2} strokeDasharray="6 6" opacity={0.75} />
            </g>
          );
        })}
      </g>

      {/* marker dots + labels sit above the clip so they stay crisp at the edges */}
      {markers.map((m, i) => {
        const op = Math.max(0, Math.min(1, m.progress ?? 1));
        if (op <= 0) return null;
        const mc = m.color ?? colors.kernel;
        return (
          <g key={`m${i}`} opacity={op}>
            {m.guides && (
              <>
                <text x={padL - 14} y={sy(m.y) + 7} textAnchor="end" style={{ fill: mc }} fontSize={21} fontFamily={fonts.sans} fontWeight={700}>
                  {fmt(m.y)}
                </text>
                <text x={sx(m.x)} y={height - padB + 32} textAnchor="middle" style={{ fill: mc }} fontSize={21} fontFamily={fonts.sans} fontWeight={700}>
                  {fmt(m.x)}
                </text>
              </>
            )}
            <circle cx={sx(m.x)} cy={sy(m.y)} r={9} style={{ fill: mc, stroke: colors.bg }} strokeWidth={3} />
            {m.label && (
              <text x={sx(m.x) + 16} y={sy(m.y) - 14} style={{ fill: colors.text }} fontSize={24} fontFamily={fonts.sans} fontWeight={700}>
                {m.label}
              </text>
            )}
          </g>
        );
      })}

      {pointAt != null && firstFn && drawProgress > 0.98 && (
        <circle cx={sx(pointAt)} cy={sy(firstFn(pointAt))} r={9} style={{ fill: colors.kernel, stroke: colors.bg }} strokeWidth={3} />
      )}

      {/* automatic legend when any series is labelled */}
      {legendEntries.length > 0 && (
        <g>
          <rect
            x={width - padR - 236}
            y={padT + 10}
            width={226}
            height={legendEntries.length * 34 + 14}
            rx={10}
            style={{ fill: alpha(colors.panel, 0.85), stroke: colors.edge }}
            strokeWidth={1}
          />
          {legendEntries.map((e, i) => (
            <g key={i}>
              <line
                x1={width - padR - 220}
                y1={padT + 34 + i * 34}
                x2={width - padR - 188}
                y2={padT + 34 + i * 34}
                style={{ stroke: e.color }}
                strokeWidth={4}
                strokeLinecap="round"
                strokeDasharray={e.dash ? "8 6" : undefined}
              />
              <text x={width - padR - 176} y={padT + 41 + i * 34} style={{ fill: colors.text }} fontSize={21} fontFamily={fonts.sans}>
                {e.label}
              </text>
            </g>
          ))}
        </g>
      )}
    </svg>
  );
};
