import React from "react";
import { alpha, colors, fonts } from "../style/tokens";

/**
 * 2D function plot — a universal STEM primitive (calculus, physics kinematics,
 * statistics, signals, economics…). Pure SVG, deterministic. Supports animated
 * curve drawing, a moving point, a tangent line, and shaded area-under-curve.
 *
 *   <Plot fn={(x) => 0.25 * x * x} xRange={[-4, 4]} yRange={[0, 4]}
 *         drawProgress={p} tangentAt={x} pointAt={x} areaTo={x} />
 */
export const Plot: React.FC<{
  fn: (x: number) => number;
  xRange: [number, number];
  yRange: [number, number];
  width?: number;
  height?: number;
  color?: string;
  drawProgress?: number; // 0..1, animates the curve being drawn
  tangentAt?: number | null; // x value to draw a tangent line at
  pointAt?: number | null; // x value to mark a dot
  areaTo?: number | null; // shade area under curve from xRange[0] up to this x
  xLabel?: string;
  yLabel?: string;
}> = ({
  fn,
  xRange,
  yRange,
  width = 760,
  height = 560,
  color = colors.user,
  drawProgress = 1,
  tangentAt = null,
  pointAt = null,
  areaTo = null,
  xLabel = "x",
  yLabel = "y",
}) => {
  const pad = 48;
  const [xMin, xMax] = xRange;
  const [yMin, yMax] = yRange;
  const sx = (x: number) => pad + ((x - xMin) / (xMax - xMin)) * (width - 2 * pad);
  const sy = (y: number) => height - pad - ((y - yMin) / (yMax - yMin)) * (height - 2 * pad);

  const N = 240;
  const pts: [number, number][] = [];
  for (let i = 0; i <= N; i++) {
    const x = xMin + ((xMax - xMin) * i) / N;
    pts.push([x, fn(x)]);
  }
  const path = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${sx(x).toFixed(1)},${sy(y).toFixed(1)}`).join(" ");

  // gridlines at integer-ish steps
  const xStep = niceStep(xMax - xMin);
  const yStep = niceStep(yMax - yMin);
  const grid: React.ReactNode[] = [];
  for (let x = Math.ceil(xMin / xStep) * xStep; x <= xMax; x += xStep) {
    grid.push(<line key={`gx${x}`} x1={sx(x)} y1={sy(yMin)} x2={sx(x)} y2={sy(yMax)} style={{ stroke: colors.edge }} strokeWidth={1} opacity={0.4} />);
  }
  for (let y = Math.ceil(yMin / yStep) * yStep; y <= yMax; y += yStep) {
    grid.push(<line key={`gy${y}`} x1={sx(xMin)} y1={sy(y)} x2={sx(xMax)} y2={sy(y)} style={{ stroke: colors.edge }} strokeWidth={1} opacity={0.4} />);
  }

  // area under curve
  let areaPath: string | null = null;
  if (areaTo != null) {
    const ap: string[] = [`M${sx(xMin)},${sy(0)}`];
    for (let i = 0; i <= N; i++) {
      const x = xMin + ((areaTo - xMin) * i) / N;
      ap.push(`L${sx(x).toFixed(1)},${sy(fn(x)).toFixed(1)}`);
    }
    ap.push(`L${sx(areaTo)},${sy(0)} Z`);
    areaPath = ap.join(" ");
  }

  // tangent line
  let tangent: React.ReactNode = null;
  if (tangentAt != null) {
    const h = 1e-3;
    const slope = (fn(tangentAt + h) - fn(tangentAt - h)) / (2 * h);
    const y0 = fn(tangentAt);
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

  const pathLen = 2600; // approximate; enough for dash animation
  return (
    <svg width={width} height={height} style={{ overflow: "visible" }}>
      {grid}
      {/* axes */}
      <line x1={sx(xMin)} y1={sy(0)} x2={sx(xMax)} y2={sy(0)} style={{ stroke: colors.muted }} strokeWidth={2} />
      <line x1={sx(0)} y1={sy(yMin)} x2={sx(0)} y2={sy(yMax)} style={{ stroke: colors.muted }} strokeWidth={2} />
      <text x={sx(xMax)} y={sy(0) + 26} style={{ fill: colors.muted }} fontSize={22} fontFamily={fonts.sans}>{xLabel}</text>
      <text x={sx(0) + 12} y={sy(yMax)} style={{ fill: colors.muted }} fontSize={22} fontFamily={fonts.sans}>{yLabel}</text>

      {areaPath && <path d={areaPath} style={{ fill: alpha(color, 0.2) }} stroke="none" />}
      <path
        d={path}
        fill="none"
        style={{ stroke: color }}
        strokeWidth={4}
        strokeLinecap="round"
        strokeDasharray={pathLen}
        strokeDashoffset={pathLen * (1 - drawProgress)}
      />
      {tangent}
      {pointAt != null && drawProgress > 0.98 && (
        <circle cx={sx(pointAt)} cy={sy(fn(pointAt))} r={9} style={{ fill: colors.kernel, stroke: colors.bg }} strokeWidth={3} />
      )}
    </svg>
  );
};

function niceStep(range: number): number {
  const raw = range / 6;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10;
  return step * mag;
}
