import React from "react";
import {interpolate, useCurrentFrame, useVideoConfig} from "remotion";
import {colors, fonts} from "../style/tokens";

export type AlignedWord = {w: string; start: number; end: number};

/** Word-accurate captions sourced from audio/en/alignment.json.
 *
 * `keywords` only opens a short caption window around narration-driven visual
 * cues; `full` keeps four-word chunks visible continuously. The layer is a
 * composition concern, so generated scenes cannot accidentally place text
 * outside the safe zone or create a second competing caption system.
 */
export const NarrationCaptions: React.FC<{
  words?: AlignedWord[];
  mode: "off" | "keywords" | "full";
  cues?: (number | null)[];
  dur: number;
}> = ({words = [], mode, cues, dur}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  if (mode === "off" || words.length === 0) return null;
  const seconds = frame / fps;
  let active = words.findIndex((word) => seconds >= word.start && seconds <= word.end + 0.06);
  if (active < 0) {
    active = words.findIndex((word) => seconds < word.start);
    active = active <= 0 ? 0 : active - 1;
  }
  const p = frame / Math.max(1, dur);
  const nearCue = (cues ?? []).some((cue) => cue != null && Math.abs(p - cue) <= 0.085);
  if (mode === "keywords" && !nearCue) return null;

  const start = Math.max(0, Math.min(words.length - 1, Math.floor(active / 4) * 4));
  const chunk = words.slice(start, start + 4);
  const word = words[active];
  const fade = word
    ? interpolate(seconds, [word.start - 0.08, word.start + 0.04, word.end + 0.12, word.end + 0.24], [0, 1, 1, 0], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : 1;
  return (
    <div
      style={{
        position: "absolute",
        left: 250,
        right: 250,
        bottom: 76,
        display: "flex",
        justifyContent: "center",
        pointerEvents: "none",
        opacity: mode === "full" ? Math.max(0.72, fade) : fade,
        zIndex: 80,
      }}
    >
      <div
        style={{
          display: "flex",
          gap: 13,
          padding: "15px 24px 17px",
          borderRadius: 18,
          background: "rgba(7, 10, 16, 0.82)",
          border: "1px solid rgba(255,255,255,0.12)",
          boxShadow: "0 16px 44px rgba(0,0,0,0.38)",
          backdropFilter: "blur(14px)",
        }}
      >
        {chunk.map((item, index) => {
          const absolute = start + index;
          const isActive = absolute === active;
          return (
            <span
              key={`${absolute}-${item.start}`}
              style={{
                color: isActive ? colors.kernel : colors.text,
                fontFamily: fonts.sans,
                fontSize: 34,
                lineHeight: 1,
                fontWeight: isActive ? 760 : 560,
                transform: `translateY(${isActive ? -2 : 0}px) scale(${isActive ? 1.045 : 1})`,
              }}
            >
              {item.w}
            </span>
          );
        })}
      </div>
    </div>
  );
};

