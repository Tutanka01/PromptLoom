import { interpolate } from "remotion";

/**
 * Beat/cue animation helpers, ported from the reference sync grammar
 * (`begin_sync` / `play_until` / `hold_until`). A scene's narration drives a
 * normalized progress p in [0, 1]; visual beats complete at cue ratios.
 */

export type Easing = "smooth" | "linear";

const smooth = (t: number): number =>
  // Manim's default smooth() = 3t^2 - 2t^3 (smoothstep)
  t * t * (3 - 2 * t);

/**
 * Progress of a beat that animates over the window [from, to] of scene
 * progress, completing exactly at the cue `to` — mirroring play_until(to).
 */
export const beat = (
  p: number,
  from: number,
  to: number,
  ease: Easing = "smooth",
): number => {
  const raw = interpolate(p, [from, to], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return ease === "smooth" ? smooth(raw) : raw;
};

/** Fade-in opacity for an element appearing across [from, to]. */
export const appear = (p: number, from: number, to: number): number => beat(p, from, to);

/** Dim from 1 → DIM at cue `at`, optionally restoring to 1 at `until`. */
export const dimAt = (
  p: number,
  at: number,
  dim: number,
  until?: number,
): number => {
  if (until !== undefined && p >= until) {
    return interpolate(p, [until - 0.04, until], [dim, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  }
  return interpolate(p, [at - 0.06, at], [1, dim], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
};

/** Fade-out at the very end of the scene (the trailing 0.7s FadeOut). */
export const tailFade = (p: number, start = 0.97): number =>
  interpolate(p, [start, 1], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
