import React from "react";
import { alpha, colors, fonts, mu, mx, my } from "../style/tokens";

/**
 * A grid of labelled cells — the workhorse primitive for low-level/kernel
 * content: memory blocks, page-table entries, registers, stack frames, byte
 * buffers. Pure render; the caller drives `reveal` (staggered appearance) and
 * per-cell `highlight` (focus glow). Coordinates are Manim units (origin
 * centred, y up), so it composes with the rest of the catalog.
 */
export type MemoryCell = { label?: string; sub?: string; color?: string; highlight?: boolean };

export const MemoryGrid: React.FC<{
  cells: MemoryCell[];
  cols?: number;
  cellW?: number; // Manim units
  cellH?: number;
  gap?: number;
  x?: number; // grid centre
  y?: number;
  reveal?: number; // 0..1 fraction of cells shown
  accent?: string;
}> = ({ cells, cols = 4, cellW = 2.0, cellH = 1.0, gap = 0.25, x = 0, y = 0, reveal = 1, accent = colors.user }) => {
  const n = cells.length;
  const colsUsed = Math.max(1, Math.min(cols, n || 1));
  const rows = Math.max(1, Math.ceil(n / colsUsed));
  const totalW = colsUsed * cellW + (colsUsed - 1) * gap;
  const totalH = rows * cellH + (rows - 1) * gap;
  const x0 = x - totalW / 2 + cellW / 2;
  const y0 = y + totalH / 2 - cellH / 2;
  const shown = Math.ceil(Math.max(0, Math.min(1, reveal)) * n);
  return (
    <>
      {cells.map((cell, i) => {
        if (i >= shown) return null;
        const r = Math.floor(i / colsUsed);
        const c = i % colsUsed;
        const cx = x0 + c * (cellW + gap);
        const cy = y0 - r * (cellH + gap);
        const col = cell.color ?? (cell.highlight ? accent : colors.edge);
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: mx(cx) - mu(cellW) / 2,
              top: my(cy) - mu(cellH) / 2,
              width: mu(cellW),
              height: mu(cellH),
              borderRadius: mu(0.08),
              background: cell.highlight ? alpha(col, 0.13) : colors.panel,
              border: `${cell.highlight ? 3 : 2}px solid ${col}`,
              boxShadow: cell.highlight ? `0 0 ${mu(0.14)}px ${alpha(col, 0.53)}` : "0 4px 14px rgba(0,0,0,0.30)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              boxSizing: "border-box",
            }}
          >
            {cell.label ? (
              <span style={{ color: colors.text, fontFamily: fonts.mono, fontSize: 26, fontWeight: 600 }}>{cell.label}</span>
            ) : null}
            {cell.sub ? (
              <span style={{ color: colors.muted, fontFamily: fonts.sans, fontSize: 17 }}>{cell.sub}</span>
            ) : null}
          </div>
        );
      })}
    </>
  );
};
