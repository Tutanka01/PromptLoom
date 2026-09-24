import React from "react";
import { colors, fonts } from "../style/tokens";

/**
 * A number that counts from 0 up to `value` as `progress` goes 0 -> 1 — for a
 * metric, throughput, memory size, syscall count, latency. Pure render;
 * tabular-nums keeps the digits from jittering as they change.
 */
export const Counter: React.FC<{
  value: number;
  progress: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  fontSize?: number;
  color?: string;
}> = ({ value, progress, prefix = "", suffix = "", decimals = 0, fontSize = 140, color = colors.text }) => {
  const current = value * Math.max(0, Math.min(1, progress));
  const text = current.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  // Prefix/suffix are units ("$", "%", " ms", " GB/s"): set smaller, in the
  // sans face, with a fixed optical gap. In the monospace number face a space
  // is ~0.6em wide, so " %" at 140px opened a hole between value and unit.
  const pre = prefix.trim();
  const suf = suffix.trim();
  const unit = (value: string, side: "left" | "right") => (
    <span
      style={{
        fontFamily: fonts.sans,
        fontSize: fontSize * 0.5,
        fontWeight: 700,
        [side === "left" ? "marginRight" : "marginLeft"]: fontSize * (/^[\p{L}]/u.test(value) ? 0.14 : 0.06),
      }}
    >
      {value}
    </span>
  );
  return (
    <span style={{ display: "inline-flex", alignItems: "baseline", fontFamily: fonts.mono, fontSize, fontWeight: 800, color, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
      {pre ? unit(pre, "left") : null}
      {text}
      {suf ? unit(suf, "right") : null}
    </span>
  );
};
