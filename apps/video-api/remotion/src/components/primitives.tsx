import React from "react";
import { AbsoluteFill } from "remotion";
import { alpha, colors, fonts, fontSize, mu, mx, my, WIDTH, HEIGHT } from "../style/tokens";

/**
 * Reusable visual primitives — the component library the generator composes.
 * Each maps closely to a helper in the reference `syscall_style.py`, but built
 * with CSS/SVG so it renders crisply and is trivial for an LLM to parameterize.
 */

const shadow = "0 6px 18px rgba(0,0,0,0.34)";

export const Background: React.FC = () => {
  // base + subtle top gradient + faint dot grid, matching make_background().
  const dots: React.ReactNode[] = [];
  for (let i = 0; i < 17; i++) {
    for (let j = 0; j < 9; j++) {
      dots.push(
        <circle
          key={`${i}-${j}`}
          cx={mx(i * 0.8 - 6.4)}
          cy={my(j * 0.8 - 3.2)}
          r={1.4}
          fill="#303848"
          opacity={0.25}
        />,
      );
    }
  }
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <AbsoluteFill
        style={{
          background: `linear-gradient(180deg, ${colors.bgTop} 0%, rgba(18,22,31,0) 45%)`,
        }}
      />
      <svg width={WIDTH} height={HEIGHT} style={{ position: "absolute" }}>
        {dots}
      </svg>
    </AbsoluteFill>
  );
};

export const TitleBar: React.FC<{ label: string; opacity?: number }> = ({
  label,
  opacity = 1,
}) => (
  <div style={{ position: "absolute", top: mu(0.34), width: WIDTH, opacity }}>
    <div
      style={{
        textAlign: "center",
        color: colors.text,
        fontFamily: fonts.sans,
        fontSize: fontSize.h2 + 4,
        fontWeight: 700,
      }}
    >
      {label}
    </div>
    <div
      style={{
        height: 2,
        width: mu(12.5),
        margin: `${mu(0.18)}px auto 0`,
        backgroundColor: "#2D3646",
      }}
    />
  </div>
);

type BoxProps = {
  x: number;
  y: number;
  w: number;
  h: number;
  accent?: string;
  fill?: string;
  radius?: number;
  opacity?: number;
  stroke?: string;
  strokeWidth?: number;
  glow?: number; // 0..1 focus glow strength
  children?: React.ReactNode;
  mono?: boolean;
  fontPx?: number;
};

/** Rounded card with a bottom accent line + drop shadow (shadowed_card). */
export const Card: React.FC<BoxProps> = ({
  x,
  y,
  w,
  h,
  accent = colors.user,
  fill = colors.panel,
  radius = 0.14,
  opacity = 1,
  stroke = colors.edge,
  strokeWidth = 2,
  glow = 0,
  children,
  mono = false,
  fontPx = fontSize.body,
}) => (
  <div
    style={{
      position: "absolute",
      left: mx(x) - mu(w) / 2,
      top: my(y) - mu(h) / 2,
      width: mu(w),
      height: mu(h),
      borderRadius: mu(radius),
      background: fill,
      border: `${strokeWidth}px solid ${stroke}`,
      boxShadow:
        glow > 0
          ? `${shadow}, 0 0 ${18 + glow * 26}px ${glow * 7}px ${alpha(accent, 0.4)}`
          : shadow,
      opacity,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      color: colors.text,
      fontFamily: mono ? fonts.mono : fonts.sans,
      fontSize: fontPx,
      fontWeight: 600,
      textAlign: "center",
      whiteSpace: "pre-line",
      lineHeight: 1.15,
      boxSizing: "border-box",
    }}
  >
    {children}
    <div
      style={{
        position: "absolute",
        bottom: mu(0.04),
        left: "12%",
        right: "12%",
        height: 3,
        background: accent,
        opacity: 0.9,
        borderRadius: 2,
      }}
    />
  </div>
);

/** Monospace, darker card for code/registers (code_card). */
export const CodeCard: React.FC<BoxProps> = (props) => (
  <Card
    {...props}
    fill={props.fill ?? "#111722"}
    radius={props.radius ?? 0.1}
    mono
    fontPx={props.fontPx ?? fontSize.code}
  />
);

export const Pill: React.FC<{
  x: number;
  y: number;
  w: number;
  label: string;
  color: string;
  opacity?: number;
}> = ({ x, y, w, label, color, opacity = 1 }) => (
  <div
    style={{
      position: "absolute",
      left: mx(x) - mu(w) / 2,
      top: my(y) - mu(0.24),
      width: mu(w),
      height: mu(0.48),
      borderRadius: mu(0.2),
      background: colors.panel2,
      border: `2px solid ${color}`,
      opacity,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      color: colors.text,
      fontFamily: fonts.sans,
      fontSize: 19,
      fontWeight: 700,
      boxSizing: "border-box",
    }}
  >
    {label}
  </div>
);

/** Concentric-circle kernel badge (kernel_badge). */
export const KernelBadge: React.FC<{
  x: number;
  y: number;
  label?: string;
  scale?: number;
  opacity?: number;
  glow?: number;
}> = ({ x, y, label = "KERNEL", scale = 1, opacity = 1, glow = 0 }) => {
  const r = mu(1.02) * scale;
  return (
    <div
      style={{
        position: "absolute",
        left: mx(x) - r,
        top: my(y) - r,
        width: r * 2,
        height: r * 2,
        borderRadius: "50%",
        border: `5px solid ${colors.kernel}`,
        opacity,
        boxShadow: glow > 0 ? `0 0 ${20 + glow * 30}px ${glow * 8}px ${alpha(colors.kernel, 0.4)}` : shadow,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          width: r * 1.35,
          height: r * 1.35,
          borderRadius: "50%",
          border: `2px solid ${colors.kernel}`,
          background: "#2A220B",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: colors.kernel,
          fontFamily: fonts.sans,
          fontSize: 24 * scale,
          fontWeight: 700,
          textAlign: "center",
          whiteSpace: "pre-line",
          lineHeight: 1.1,
        }}
      >
        {label}
      </div>
    </div>
  );
};

export const HardwareBox: React.FC<{
  x: number;
  y: number;
  w: number;
  h: number;
  icon: string;
  label: string;
  opacity?: number;
}> = ({ x, y, w, h, icon, label, opacity = 1 }) => (
  <div
    style={{
      position: "absolute",
      left: mx(x) - mu(w) / 2,
      top: my(y) - mu(h) / 2,
      width: mu(w),
      height: mu(h),
      borderRadius: mu(0.12),
      background: colors.panel2,
      border: `2px solid ${colors.edge}`,
      boxShadow: shadow,
      opacity,
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      gap: 6,
      boxSizing: "border-box",
    }}
  >
    <div style={{ color: colors.kernel, fontFamily: fonts.sans, fontSize: 28, fontWeight: 700 }}>
      {icon}
    </div>
    <div style={{ color: colors.text, fontFamily: fonts.sans, fontSize: 19 }}>{label}</div>
    <div
      style={{
        position: "absolute",
        bottom: mu(0.04),
        left: "12%",
        right: "12%",
        height: 3,
        background: colors.hardware,
        borderRadius: 2,
      }}
    />
  </div>
);

export const Zone: React.FC<{
  x: number;
  y: number;
  w: number;
  h: number;
  color: string;
  fill: string;
  opacity?: number;
  strokeWidth?: number;
  label?: string;
  labelPos?: "top" | "inside-tl";
}> = ({ x, y, w, h, color, fill, opacity = 1, strokeWidth = 2, label, labelPos = "top" }) => (
  <>
    <div
      style={{
        position: "absolute",
        left: mx(x) - mu(w) / 2,
        top: my(y) - mu(h) / 2,
        width: mu(w),
        height: mu(h),
        borderRadius: mu(0.16),
        background: fill,
        border: `${strokeWidth}px solid ${color}`,
        opacity,
        boxSizing: "border-box",
      }}
    />
    {label && labelPos === "top" && (
      <div
        style={{
          position: "absolute",
          left: 0,
          width: WIDTH,
          top: my(y + h / 2) - mu(0.5),
          textAlign: "center",
          color,
          fontFamily: fonts.sans,
          fontSize: fontSize.caption,
          fontWeight: 700,
          opacity,
        }}
      >
        {label}
      </div>
    )}
    {label && labelPos === "inside-tl" && (
      <div
        style={{
          position: "absolute",
          left: mx(x - w / 2) + mu(0.5),
          top: my(y + h / 2) + mu(0.35),
          color,
          fontFamily: fonts.sans,
          fontSize: fontSize.h2,
          fontWeight: 700,
          opacity,
        }}
      >
        {label}
      </div>
    )}
  </>
);

/** SVG arrow between two Manim points, with optional draw progress 0..1. */
export const Arrow: React.FC<{
  from: [number, number];
  to: [number, number];
  color: string;
  width?: number;
  progress?: number;
  dashed?: boolean;
  opacity?: number;
}> = ({ from, to, color, width = 3.5, progress = 1, dashed = false, opacity = 1 }) => {
  const x1 = mx(from[0]);
  const y1 = my(from[1]);
  const x2f = mx(to[0]);
  const y2f = my(to[1]);
  const x2 = x1 + (x2f - x1) * progress;
  const y2 = y1 + (y2f - y1) * progress;
  // Coordinate-based id (not colour-based): `color` may be a `var(--c-*)` token,
  // which is not a valid SVG id/URL fragment.
  const id = `arrow-${Math.round(x1)}-${Math.round(y1)}-${Math.round(x2f)}-${Math.round(y2f)}`;
  return (
    <svg width={WIDTH} height={HEIGHT} style={{ position: "absolute", overflow: "visible", opacity }}>
      <defs>
        <marker id={id} markerWidth="10" markerHeight="10" refX="7" refY="3" orient="auto" markerUnits="strokeWidth">
          <path d="M0,0 L7,3 L0,6 Z" style={{ fill: color }} />
        </marker>
      </defs>
      <line
        x1={x1}
        y1={y1}
        x2={x2}
        y2={y2}
        style={{ stroke: color }}
        strokeWidth={width}
        strokeDasharray={dashed ? "10 8" : undefined}
        markerEnd={progress > 0.85 ? `url(#${id})` : undefined}
      />
    </svg>
  );
};

export const Terminal: React.FC<{
  x: number;
  y: number;
  w: number;
  h: number;
  text: string;
  typed?: number; // 0..1 fraction of text revealed
  opacity?: number;
}> = ({ x, y, w, h, text, typed = 1, opacity = 1 }) => {
  const shown = text.slice(0, Math.ceil(text.length * typed));
  return (
    <div
      style={{
        position: "absolute",
        left: mx(x) - mu(w) / 2,
        top: my(y) - mu(h) / 2,
        width: mu(w),
        height: mu(h),
        borderRadius: mu(0.16),
        background: "#101722",
        border: `2px solid ${colors.user}`,
        opacity,
        display: "flex",
        alignItems: "center",
        paddingLeft: mu(0.4),
        color: colors.text,
        fontFamily: fonts.mono,
        fontSize: fontSize.code + 4,
        boxSizing: "border-box",
      }}
    >
      {shown}
      <span
        style={{
          display: "inline-block",
          width: 10,
          height: fontSize.code + 6,
          marginLeft: 6,
          background: colors.user,
        }}
      />
    </div>
  );
};

/** A red ✕ cross mark centered at a Manim point. */
export const CrossMark: React.FC<{ x: number; y: number; size?: number; opacity?: number }> = ({
  x,
  y,
  size = 0.44,
  opacity = 1,
}) => (
  <div
    style={{
      position: "absolute",
      left: mx(x) - mu(size) / 2,
      top: my(y) - mu(size) / 2,
      width: mu(size),
      height: mu(size),
      opacity,
      color: colors.danger,
      fontSize: mu(size),
      lineHeight: `${mu(size)}px`,
      fontWeight: 900,
      textAlign: "center",
    }}
  >
    ✕
  </div>
);

export const Caption: React.FC<{
  x: number;
  y: number;
  label: string;
  color: string;
  size?: number;
  bold?: boolean;
  opacity?: number;
  width?: number;
}> = ({ x, y, label, color, size = fontSize.caption, bold = true, opacity = 1, width = 6 }) => (
  <div
    style={{
      position: "absolute",
      left: mx(x) - mu(width) / 2,
      top: my(y) - size / 2,
      width: mu(width),
      textAlign: "center",
      color,
      fontFamily: fonts.sans,
      fontSize: size,
      fontWeight: bold ? 700 : 400,
      opacity,
    }}
  >
    {label}
  </div>
);
