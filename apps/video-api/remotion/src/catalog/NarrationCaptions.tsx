import React from "react";
import {interpolate, useCurrentFrame, useVideoConfig} from "remotion";
import {colors, fonts} from "../style/tokens";

/** One spoken word of a cue, with its global (whole-video) timing in seconds. */
export type CaptionWord = {text: string; start: number; end: number};

/** A subtitle cue: 1-2 already-wrapped lines plus its on-screen window. */
export type CaptionCue = {start: number; end: number; lines: CaptionWord[][]};

/**
 * Single, continuous subtitle track for the whole video.
 *
 * It is mounted ONCE at the top level of the composition (outside the per-scene
 * `SceneFrame`), so it neither fades with scene transitions nor depends on
 * per-scene beats — the previous per-scene, beat-gated rendering made subtitles
 * appear and vanish unevenly. Cues are the global list pre-built in Python
 * (pipeline/captions.py -> subtitles.json), the same source as the .srt/.vtt, so
 * the burned-in track and the sidecar can never disagree.
 *
 * `off` hides the track; `full` and `keywords` both render continuously (any
 * active cue is shown). This component only picks the active cue, fades it at
 * its edges, and karaoke-highlights the word currently being spoken.
 */
export const SubtitleTrack: React.FC<{
  cues?: CaptionCue[];
  mode: "off" | "keywords" | "full";
}> = ({cues = [], mode}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  if (mode === "off" || cues.length === 0) return null;
  const seconds = frame / fps;

  const active = cues.find((cue) => seconds >= cue.start - 0.04 && seconds <= cue.end + 0.04);
  if (!active) return null;

  const fade = interpolate(
    seconds,
    [active.start - 0.12, active.start + 0.06, active.end - 0.05, active.end + 0.16],
    [0, 1, 1, 0],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp"},
  );

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
        opacity: fade,
        zIndex: 90,
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 6,
          padding: "15px 26px 17px",
          borderRadius: 18,
          maxWidth: "100%",
          background: "rgba(7, 10, 16, 0.82)",
          border: "1px solid rgba(255,255,255,0.12)",
          boxShadow: "0 16px 44px rgba(0,0,0,0.40)",
          backdropFilter: "blur(14px)",
        }}
      >
        {active.lines.map((line, lineIndex) => (
          <div
            key={lineIndex}
            style={{display: "flex", gap: 13, justifyContent: "center", flexWrap: "nowrap"}}
          >
            {line.map((word, wordIndex) => {
              const isActive = seconds >= word.start && seconds <= word.end + 0.06;
              return (
                <span
                  key={`${lineIndex}-${wordIndex}-${word.start}`}
                  style={{
                    color: isActive ? colors.kernel : colors.text,
                    fontFamily: fonts.sans,
                    fontSize: 34,
                    lineHeight: 1.16,
                    whiteSpace: "pre",
                    fontWeight: isActive ? 760 : 560,
                    textShadow: "0 2px 10px rgba(0,0,0,0.55)",
                    transform: `translateY(${isActive ? -2 : 0}px) scale(${isActive ? 1.045 : 1})`,
                  }}
                >
                  {word.text}
                </span>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
};
