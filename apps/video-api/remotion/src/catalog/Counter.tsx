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
  return (
    <span style={{ fontFamily: fonts.mono, fontSize, fontWeight: 800, color, fontVariantNumeric: "tabular-nums" }}>
      {prefix}
      {text}
      {suffix}
    </span>
  );
};
