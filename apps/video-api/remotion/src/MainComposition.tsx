import React from "react";
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { z } from "zod";
import { AmbientBackground } from "./catalog/AmbientBackground";
import { SubtitleTrack } from "./catalog/NarrationCaptions";
import { SCENE_COMPONENTS } from "./registry";
import { applyThemeVars, colors } from "./style/tokens";

/**
 * Data-driven main composition. Reads the per-job `video.json` (here passed as
 * input props): an ordered list of scenes, each naming a registered component +
 * its props, an optional transition name, an optional audio file, and a
 * duration in frames derived from `audio/en/durations.json`. Renders one
 * <Sequence> per scene.
 *
 * For the spike, scenes embed their narration <Audio> directly so the rendered
 * MP4 is self-contained. In production the render is silent and `assemble_en.sh`
 * muxes the global voiceover (matching the existing Manim flow).
 */

export const sceneSchema = z.object({
  component: z.string(),
  props: z.record(z.unknown()).default({}),
  durationInFrames: z.number().int().positive(),
  transition: z.string().optional(),
  audio: z.string().optional(),
});

const captionWordSchema = z.object({ text: z.string(), start: z.number(), end: z.number() });
const captionCueSchema = z.object({
  start: z.number(),
  end: z.number(),
  lines: z.array(z.array(captionWordSchema)),
});

export const videoSchema = z.object({
  scenes: z.array(sceneSchema),
  embedAudio: z.boolean().default(false),
  captionMode: z.enum(["off", "keywords", "full"]).default("off"),
  // One global, whole-video cue list (pipeline/captions.py -> subtitles.json),
  // rendered as a single continuous top-level track.
  subtitles: z.array(captionCueSchema).default([]),
  transitionProfile: z.enum(["minimal", "editorial", "cinematic"]).default("minimal"),
  // Art-direction palette (see THEMES in style/tokens.ts). A plain string with a
  // safe fallback: unknown values resolve to the default palette in
  // applyThemeVars, and the allowed set is enforced upstream in the pipeline.
  theme: z.string().default("default"),
});

export type VideoProps = z.infer<typeof videoSchema>;

// `registry` is supplied in code by the per-job entry (palette + this job's
// Custom scenes); it is intentionally NOT part of the Zod input-props schema.
type MainCompositionProps = VideoProps & {
  registry?: Record<string, React.FC<Record<string, unknown>>>;
};

export const TRANSITIONS = ["fade", "rise", "slide-left", "scale", "slide-right", "wipe"] as const;
export type TransitionName = (typeof TRANSITIONS)[number];

const smooth = (t: number): number => t * t * (3 - 2 * t);

/**
 * Per-scene envelope + transition. Scenes never overlap on the timeline (the
 * sequentially-muxed voiceover must stay in sync), so a "transition" is an
 * exit animation toward the persistent ambient background followed by the next
 * scene's entrance — visually a styled hand-off, never a hard cut. Entry/exit
 * windows are relative to the scene but capped in absolute time so long scenes
 * still settle quickly. `auto` cycles deterministically by scene index, so two
 * consecutive scenes never share a transition.
 */
const SceneFrame: React.FC<{
  dur: number;
  index: number;
  transition?: string;
  children: React.ReactNode;
}> = ({ dur, index, transition, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const name: TransitionName =
    transition && transition !== "auto" && (TRANSITIONS as readonly string[]).includes(transition)
      ? (transition as TransitionName)
      : TRANSITIONS[index % TRANSITIONS.length];

  const inFrames = Math.max(1, Math.min(0.08 * dur, 0.7 * fps));
  const outFrames = Math.max(1, Math.min(0.07 * dur, 0.8 * fps));
  const enter = smooth(
    interpolate(frame, [0, inFrames], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
  );
  const exit = smooth(
    interpolate(frame, [dur - outFrames, dur - 1], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
  );

  let transform = "";
  let clipPath: string | undefined;
  if (name === "rise") {
    transform = `translateY(${(1 - enter) * 46 - (1 - exit) * 30}px)`;
  } else if (name === "slide-left") {
    transform = `translateX(${(1 - enter) * 60 - (1 - exit) * 50}px)`;
  } else if (name === "slide-right") {
    transform = `translateX(${-(1 - enter) * 60 + (1 - exit) * 50}px)`;
  } else if (name === "scale") {
    transform = `scale(${0.95 + enter * 0.05 + (1 - exit) * 0.025})`;
  } else if (name === "wipe") {
    clipPath = enter < 1 ? `inset(0 ${(1 - enter) * 100}% 0 0)` : undefined;
  }

  return (
    <AbsoluteFill style={{ opacity: enter * exit, transform: transform || undefined, clipPath }}>
      {children}
    </AbsoluteFill>
  );
};

/** A cut-cover overlay that never changes timeline length. It is deliberately
 * rendered as a top-level Sequence around a scene boundary instead of a
 * TransitionSeries overlap, preserving the audio-derived scene starts. */
const CutOverlay: React.FC<{dur: number; index: number; profile: "editorial" | "cinematic"}> = ({dur, index, profile}) => {
  const frame = useCurrentFrame();
  const x = frame / Math.max(1, dur - 1);
  const peak = interpolate(x, [0, 0.36, 0.5, 0.64, 1], [0, 0.08, profile === "cinematic" ? 0.52 : 0.28, 0.08, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const style = index % 2;
  const background = style === 0
    ? "radial-gradient(ellipse at 72% 48%, rgba(255,190,11,.82), rgba(251,86,7,.34) 22%, transparent 58%)"
    : "linear-gradient(105deg, transparent 25%, rgba(58,134,255,.34) 45%, rgba(236,241,248,.58) 51%, rgba(155,93,229,.24) 58%, transparent 76%)";
  const shift = interpolate(x, [0, 1], style === 0 ? [-90, 90] : [-320, 320]);
  return (
    <AbsoluteFill
      style={{
        opacity: peak,
        background,
        transform: `translateX(${shift}px) scale(${1 + peak * 0.04})`,
        filter: "blur(10px)",
        mixBlendMode: "screen",
        pointerEvents: "none",
      }}
    />
  );
};

export const MainComposition: React.FC<MainCompositionProps> = ({
  scenes,
  embedAudio,
  captionMode,
  subtitles,
  transitionProfile,
  theme,
  registry,
}) => {
  const components = registry ?? SCENE_COMPONENTS;
  let cursor = 0;
  const scheduled = scenes.map((scene) => {
    const start = cursor;
    cursor += scene.durationInFrames;
    return {scene, start};
  });
  const {fps} = useVideoConfig();
  const overlayFrames = Math.max(12, Math.round(fps * 0.36));
  return (
    <AbsoluteFill style={{ ...applyThemeVars(theme), backgroundColor: colors.bg }}>
      {/* Persistent living background, BEHIND every scene. SceneFrame fades each
          scene's content in/out at its edges; during that dip this continuous
          background shows through, so scene-to-scene boundaries hand off
          smoothly instead of hard-cutting — and there is never a black or
          frozen frame between scenes (keeps freezedetect happy). No timeline
          overlap, so the per-segment voiceover stays perfectly in sync. */}
      <AmbientBackground />
      {scheduled.map(({scene, start}, i) => {
        const Comp = components[scene.component];
        if (!Comp) {
          return null;
        }
        return (
          <Sequence key={i} from={start} durationInFrames={scene.durationInFrames} name={scene.component}>
            {embedAudio && scene.audio ? <Audio src={staticFile(scene.audio)} /> : null}
            <SceneFrame dur={scene.durationInFrames} index={i} transition={scene.transition}>
              <Comp dur={scene.durationInFrames} {...scene.props} />
            </SceneFrame>
          </Sequence>
        );
      })}
      {transitionProfile !== "minimal"
        ? scheduled.slice(1).map(({start}, index) => (
            <Sequence
              key={`cut-${index}`}
              from={Math.max(0, start - Math.floor(overlayFrames / 2))}
              durationInFrames={overlayFrames}
              name={`Cut overlay ${index + 1}`}
            >
              <CutOverlay dur={overlayFrames} index={index} profile={transitionProfile} />
            </Sequence>
          ))
        : null}
      {/* One continuous subtitle track over the WHOLE timeline, on top of every
          scene and overlay. Not wrapped in a Sequence, so it reads the global
          frame and never fades with scene transitions. */}
      <SubtitleTrack cues={subtitles} mode={captionMode} />
    </AbsoluteFill>
  );
};
