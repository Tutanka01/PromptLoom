import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { alpha, colors, WIDTH, HEIGHT } from "../style/tokens";

/**
 * Living background with continuous, slow motion. Unlike a static fill, every
 * frame differs slightly — this fixes the class of bug where a near-static
 * scene (a held diagram, a tiny moving token) trips `freezedetect`, the way the
 * Manim reference did. The motion is subtle enough never to distract: a drifting
 * dot grid plus a soft glow that slowly orbits.
 */
export const AmbientBackground: React.FC<{ accent?: string }> = ({ accent = colors.user }) => {
  const frame = useCurrentFrame();

  // Slow orbiting glow.
  const gx = WIDTH / 2 + Math.cos(frame * 0.006) * 380;
  const gy = HEIGHT / 2 + Math.sin(frame * 0.0085) * 220;

  // Drifting dot grid (wraps seamlessly).
  const drift = (frame * 0.25) % 64;
  const dots: React.ReactNode[] = [];
  for (let i = -1; i < 31; i++) {
    for (let j = -1; j < 18; j++) {
      const x = i * 64 + drift;
      const y = j * 64 + (drift * 0.5);
      const tw = 0.18 + 0.12 * Math.sin(frame * 0.04 + i * 0.7 + j * 0.5);
      dots.push(<circle key={`${i}-${j}`} cx={x} cy={y} r={1.6} fill="#36405a" opacity={tw} />);
    }
  }

  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(720px 520px at ${gx}px ${gy}px, ${alpha(accent, 0.12)} 0%, rgba(0,0,0,0) 70%)`,
        }}
      />
      <AbsoluteFill
        style={{ background: `linear-gradient(180deg, ${colors.bgTop} 0%, rgba(13,16,23,0) 42%)` }}
      />
      <svg width={WIDTH} height={HEIGHT} style={{ position: "absolute" }}>
        {dots}
      </svg>
    </AbsoluteFill>
  );
};
