/**
 * Text reveal animations — curated, lightly adapted from the MIT-licensed
 * community collection `ali-abassi/remotion-templates` (examples/text-animations.tsx),
 * which is explicitly published as a Remotion skill for AI coding agents.
 *
 * These are part of the *proposal palette*: the generator can compose them
 * directly, or use them as worked examples when authoring a bespoke scene.
 * Off-brand effects (glitch/RGB-split) were dropped to keep the pedagogical,
 * dark-academic house style.
 */
import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { fonts } from "../style/tokens";

interface TextProps {
  text: string;
  fontSize?: number;
  color?: string;
  fontFamily?: string;
  delay?: number;
}

/** Word-by-word fade + slide-up. Good for narration-synced headings. */
export const TextReveal: React.FC<TextProps & { staggerDelay?: number }> = ({
  text,
  fontSize = 64,
  color = "#ffffff",
  fontFamily = fonts.sans,
  delay = 0,
  staggerDelay = 5,
}) => {
  const frame = useCurrentFrame();
  const words = text.split(" ");
  return (
    <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 16 }}>
      {words.map((word, index) => {
        const wordDelay = delay + index * staggerDelay;
        const progress = interpolate(frame - wordDelay, [0, 15], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        return (
          <span
            key={index}
            style={{
              fontSize,
              fontWeight: 700,
              fontFamily,
              color,
              opacity: progress,
              transform: `translateY(${interpolate(progress, [0, 1], [30, 0])}px)`,
            }}
          >
            {word}
          </span>
        );
      })}
    </div>
  );
};

/** Character-by-character typewriter, with a blinking cursor. Great for commands. */
export const TypewriterText: React.FC<TextProps & { speed?: number; showCursor?: boolean }> = ({
  text,
  fontSize = 48,
  color = "#ffffff",
  fontFamily = fonts.mono,
  delay = 0,
  speed = 3,
  showCursor = true,
}) => {
  const frame = useCurrentFrame();
  const adjusted = Math.max(0, frame - delay);
  const charsToShow = Math.floor(adjusted / speed);
  const displayText = text.slice(0, charsToShow);
  const cursorVisible = Math.floor(frame / 15) % 2 === 0;
  return (
    <span style={{ fontSize, fontFamily, color, fontWeight: 500 }}>
      {displayText}
      {showCursor && <span style={{ opacity: cursorVisible ? 1 : 0 }}>|</span>}
    </span>
  );
};

/** Word-by-word blur-to-sharp reveal. Calm, premium feel for key statements. */
export const BlurReveal: React.FC<TextProps & { blurAmount?: number }> = ({
  text,
  fontSize = 64,
  color = "#ffffff",
  fontFamily = fonts.sans,
  delay = 0,
  blurAmount = 18,
}) => {
  const frame = useCurrentFrame();
  const words = text.split(" ");
  return (
    <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 12 }}>
      {words.map((word, index) => {
        const wordDelay = delay + index * 8;
        const progress = interpolate(frame - wordDelay, [0, 20], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        return (
          <span
            key={index}
            style={{
              fontSize,
              fontWeight: 700,
              fontFamily,
              color,
              opacity: progress,
              filter: `blur(${interpolate(progress, [0, 1], [blurAmount, 0])}px)`,
            }}
          >
            {word}
          </span>
        );
      })}
    </div>
  );
};

/** Spring scale-in. Use sparingly for a single emphasized term. */
export const ScaleBounce: React.FC<TextProps> = ({
  text,
  fontSize = 72,
  color = "#ffffff",
  fontFamily = fonts.sans,
  delay = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const scale = spring({ frame: frame - delay, fps, config: { damping: 10, stiffness: 200 } });
  const opacity = interpolate(frame - delay, [0, 10], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <span style={{ fontSize, fontWeight: 900, fontFamily, color, display: "inline-block", transform: `scale(${scale})`, opacity }}>
      {text}
    </span>
  );
};
