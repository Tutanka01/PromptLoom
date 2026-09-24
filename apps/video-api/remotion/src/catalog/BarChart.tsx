import React from "react";
import { fitTogether, measureText, wrapText } from "../style/fit";
import { colors, fonts } from "../style/tokens";

/**
 * Animated bar chart for quantities, benchmarks, comparisons — the complement
 * to `Plot` (which draws continuous curves). Deterministic HTML layout.
 *
 * - Simple: `bars` (one value per category).
 * - Grouped: `groups` (categories) x `series` (one value per group each), with
 *   an automatic legend — e.g. models x methods in a benchmark table.
 *
 * Labels never collide: they are fitted to their slot (uniform size, up to two
 * lines) and, when they are too long for columns, the chart turns horizontal
 * (labels in a left column, bars growing to the right) — the standard layout
 * for long category names. `grow` (0..1) animates every bar; `reveal` (one
 * 0..1 per category) animates each category on its own narration cue.
 */
export type Bar = { label: string; value: number; color?: string };
export type BarSeries = { label: string; values: number[]; color?: string };

const PALETTE = [colors.user, colors.success, colors.kernel, colors.purple, colors.danger];

type Category = { label: string; items: { value: number; color: string }[] };

const decimalsOf = (values: number[]): number => {
  let d = 0;
  for (const v of values) {
    while (d < 2 && Math.abs(v * 10 ** d - Math.round(v * 10 ** d)) > 1e-6) d += 1;
  }
  return d;
};

const unitSuffix = (unit?: string): string => {
  const u = (unit ?? "").trim();
  if (!u) return "";
  // "12 ms", "2 007 MiB" — but "97%", "3.5×", "40°".
  return /^[\p{L}\p{N}]/u.test(u) ? `\u00a0${u}` : u;
};

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));

export const BarChart: React.FC<{
  bars?: Bar[];
  groups?: string[];
  series?: BarSeries[];
  width?: number;
  height?: number;
  grow?: number;
  /** Per-category growth 0..1 (overrides `grow`), e.g. one per narration cue. */
  reveal?: number[];
  maxValue?: number;
  unit?: string;
}> = ({ bars = [], groups, series, width = 1100, height = 560, grow = 1, reveal, maxValue, unit }) => {
  const grouped = Boolean(groups && groups.length && series && series.length);
  const cats: Category[] = grouped
    ? groups!.map((label, gi) => ({
        label,
        items: series!.map((s, si) => ({ value: s.values[gi] ?? 0, color: s.color ?? PALETTE[si % PALETTE.length] })),
      }))
    : bars.map((b, i) => ({ label: b.label, items: [{ value: b.value, color: b.color ?? PALETTE[i % PALETTE.length] }] }));
  const legend = grouped ? series!.map((s, si) => ({ label: s.label, color: s.color ?? PALETTE[si % PALETTE.length] })) : [];
  const n = Math.max(1, cats.length);
  const k = Math.max(1, ...cats.map((c) => c.items.length));
  const all = cats.flatMap((c) => c.items.map((it) => it.value));
  const max = maxValue ?? Math.max(1e-9, ...all);
  const decimals = decimalsOf(all);
  const suffix = unitSuffix(unit);
  const format = (v: number): string => `${v.toFixed(decimals)}${suffix}`;
  const growOf = (i: number): number => clamp01(reveal?.[i] ?? grow);

  const legendH = legend.length ? 58 : 0;
  const labelOpts = { maxLines: 2, max: 28, min: 18, weight: 600 };
  const labels = cats.map((c) => c.label);

  // Vertical columns when every label fits its slot on <= 2 lines.
  const slot = width / n;
  const colFit = fitTogether(labels, { ...labelOpts, width: slot - 18, min: 20 });
  const vertical = colFit.fits;

  const legendRow = legend.length ? (
    <div style={{ position: "absolute", left: 0, top: 0, width, height: legendH, display: "flex", justifyContent: "center", alignItems: "center", gap: 36 }}>
      {legend.map((l, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ width: 22, height: 22, borderRadius: 5, background: l.color }} />
          <span style={{ color: colors.text, fontFamily: fonts.sans, fontSize: 26, fontWeight: 600 }}>{l.label}</span>
        </div>
      ))}
    </div>
  ) : null;

  if (vertical) {
    const labelSize = colFit.fontSize;
    const labelH = colFit.lines * labelSize * 1.18 + 16;
    const valueH = 44;
    const top = legendH + valueH;
    const baseY = height - labelH;
    const plotH = Math.max(40, baseY - top);
    const cluster = Math.min(slot * 0.72, k * 150);
    const innerGap = k > 1 ? 6 : 0;
    const barW = (cluster - innerGap * (k - 1)) / k;
    const valueSize = fitTogether(all.map(format), { width: barW + innerGap, maxLines: 1, max: 28, min: 15, weight: 700 }).fontSize;
    return (
      <div style={{ position: "relative", width, height }}>
        {legendRow}
        <div style={{ position: "absolute", left: 0, top: baseY, width, height: 2, background: colors.edge }} />
        {cats.map((c, i) => {
          const g = growOf(i);
          const x0 = i * slot + (slot - cluster) / 2;
          return (
            <React.Fragment key={i}>
              {c.items.map((it, j) => {
                const h = (Math.max(0, it.value) / max) * plotH * g;
                const x = x0 + j * (barW + innerGap);
                return (
                  <React.Fragment key={j}>
                    <div style={{ position: "absolute", left: x, top: baseY - h, width: barW, height: h, borderRadius: "8px 8px 0 0", background: it.color, opacity: 0.92 }} />
                    <div
                      style={{
                        position: "absolute",
                        left: x - innerGap / 2,
                        width: barW + innerGap,
                        top: baseY - h - valueSize * 1.25 - 6,
                        textAlign: "center",
                        color: colors.text,
                        fontFamily: fonts.sans,
                        fontSize: valueSize,
                        fontWeight: 700,
                        fontVariantNumeric: "tabular-nums",
                        whiteSpace: "nowrap",
                        opacity: clamp01(g * 3),
                      }}
                    >
                      {format(it.value * g)}
                    </div>
                  </React.Fragment>
                );
              })}
              <div
                style={{
                  position: "absolute",
                  left: i * slot + 9,
                  width: slot - 18,
                  top: baseY + 12,
                  textAlign: "center",
                  color: colors.text,
                  fontFamily: fonts.sans,
                  fontSize: labelSize,
                  fontWeight: 600,
                  lineHeight: 1.18,
                  textWrap: "balance",
                  overflowWrap: "anywhere",
                  opacity: clamp01(g * 3),
                }}
              >
                {c.label}
              </div>
            </React.Fragment>
          );
        })}
      </div>
    );
  }

  // Horizontal rows: label column on the left, value after the bar's end.
  const labelColMax = width * 0.38;
  const rowH = (height - legendH) / n;
  const rowFit = fitTogether(labels, { ...labelOpts, width: labelColMax, height: rowH - 8 });
  const labelSize = rowFit.fontSize;
  const labelW = Math.min(labelColMax, Math.max(...labels.map((l) => wrapText(l, labelSize, labelColMax * 0.96).widest)) + 8);
  const thick = Math.min(52, (rowH * 0.7) / k);
  const innerGap = k > 1 ? 4 : 0;
  const valueSize = Math.max(18, Math.min(28, Math.round(thick * 0.62)));
  const valueW = Math.max(...all.map((v) => measureText(format(v), valueSize, 700))) + 18;
  const x0 = labelW + 26;
  const barMax = Math.max(40, width - x0 - valueW);
  return (
    <div style={{ position: "relative", width, height }}>
      {legendRow}
      <div style={{ position: "absolute", left: x0 - 2, top: legendH, width: 2, height: height - legendH, background: colors.edge }} />
      {cats.map((c, i) => {
        const g = growOf(i);
        const rowTop = legendH + i * rowH;
        const clusterH = k * thick + (k - 1) * innerGap;
        const y0 = rowTop + (rowH - clusterH) / 2;
        return (
          <React.Fragment key={i}>
            <div
              style={{
                position: "absolute",
                left: 0,
                width: labelW,
                top: rowTop,
                height: rowH,
                display: "flex",
                alignItems: "center",
                justifyContent: "flex-end",
                textAlign: "right",
                color: colors.text,
                fontFamily: fonts.sans,
                fontSize: labelSize,
                fontWeight: 600,
                lineHeight: 1.18,
                textWrap: "balance",
                overflowWrap: "anywhere",
                opacity: clamp01(g * 3),
              }}
            >
              {c.label}
            </div>
            {c.items.map((it, j) => {
              const w = (Math.max(0, it.value) / max) * barMax * g;
              const y = y0 + j * (thick + innerGap);
              return (
                <React.Fragment key={j}>
                  <div style={{ position: "absolute", left: x0, top: y, width: w, height: thick, borderRadius: "0 8px 8px 0", background: it.color, opacity: 0.92 }} />
                  <div
                    style={{
                      position: "absolute",
                      left: x0 + w + 10,
                      top: y + thick / 2 - valueSize * 0.62,
                      color: colors.text,
                      fontFamily: fonts.sans,
                      fontSize: valueSize,
                      fontWeight: 700,
                      fontVariantNumeric: "tabular-nums",
                      whiteSpace: "nowrap",
                      opacity: clamp01(g * 3),
                    }}
                  >
                    {format(it.value * g)}
                  </div>
                </React.Fragment>
              );
            })}
          </React.Fragment>
        );
      })}
    </div>
  );
};
