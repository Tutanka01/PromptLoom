import React from "react";
import { alpha, colors, fonts, mu, mx, my } from "../style/tokens";

/**
 * A token/packet travelling from `from` to `to` (Manim coords) at `progress`
 * 0..1 — data flow, a syscall crossing the boundary, a network packet, a value
 * moving between registers. Route it ABOVE/BELOW the row it describes so it
 * never covers a label (see remotion-skill house rules). Pure render.
 */
export const FlowToken: React.FC<{
  from: [number, number];
  to: [number, number];
  progress: number;
  color?: string;
  label?: string;
  size?: number; // Manim units (diameter)
  opacity?: number;
}> = ({ from, to, progress, color = colors.success, label, size = 0.42, opacity = 1 }) => {
  const t = Math.max(0, Math.min(1, progress));
  const x = from[0] + (to[0] - from[0]) * t;
  const y = from[1] + (to[1] - from[1]) * t;
  const d = mu(size);
  return (
    <div
      style={{
        position: "absolute",
        left: mx(x) - d / 2,
        top: my(y) - d / 2,
        width: d,
        height: d,
        borderRadius: "50%",
        background: color,
        boxShadow: `0 0 ${d * 0.7}px ${alpha(color, 0.67)}`,
        opacity,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "#0D1017",
        fontFamily: fonts.mono,
        fontSize: 18,
        fontWeight: 700,
      }}
    >
      {label ?? ""}
    </div>
  );
};
