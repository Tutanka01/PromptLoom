import React from "react";
import { colors, fonts } from "../style/tokens";

/**
 * Animated bar chart for quantities, benchmarks, comparisons — the complement
 * to `Plot` (which draws continuous curves). `grow` 0..1 animates bar heights
 * and counts the value labels up. Pure SVG, deterministic.
 */
export type Bar = { label: string; value: number; color?: string };

const PALETTE = [colors.user, colors.success, colors.kernel, colors.purple, colors.danger];

export const BarChart: React.FC<{
  bars: Bar[];
  width?: number;
  height?: number;
  grow?: number;
  maxValue?: number;
}> = ({ bars, width = 1100, height = 560, grow = 1, maxValue }) => {
  const g = Math.max(0, Math.min(1, grow));
  const max = maxValue ?? Math.max(1, ...bars.map((b) => b.value));
  const n = bars.length || 1;
  const gap = 28;
  const barW = (width - gap * (n + 1)) / n;
  const baseY = height - 60;
  return (
    <svg width={width} height={height} style={{ overflow: "visible" }}>
      <line x1={0} y1={baseY} x2={width} y2={baseY} style={{ stroke: colors.edge }} strokeWidth={2} />
      {bars.map((b, i) => {
        const h = (b.value / max) * (baseY - 40) * g;
        const x = gap + i * (barW + gap);
        const col = b.color ?? PALETTE[i % PALETTE.length];
        return (
          <g key={i}>
            <rect x={x} y={baseY - h} width={barW} height={h} rx={8} style={{ fill: col }} opacity={0.92} />
            <text x={x + barW / 2} y={baseY + 32} style={{ fill: colors.text }} fontSize={24} fontFamily={fonts.sans} fontWeight={600} textAnchor="middle">
              {b.label}
            </text>
            <text x={x + barW / 2} y={baseY - h - 14} style={{ fill: colors.muted }} fontSize={22} fontFamily={fonts.mono} textAnchor="middle" opacity={g}>
              {Number.isInteger(b.value) ? Math.round(b.value * g) : (b.value * g).toFixed(1)}
            </text>
          </g>
        );
      })}
    </svg>
  );
};
