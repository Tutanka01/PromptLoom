import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile } from "remotion";
import { z } from "zod";
import { AmbientBackground } from "./catalog/AmbientBackground";
import { SCENE_COMPONENTS } from "./registry";
import { colors } from "./style/tokens";

/**
 * Data-driven main composition. Reads the per-job `video.json` (here passed as
 * input props): an ordered list of scenes, each naming a registered component +
 * its props, an optional audio file, and a duration in frames derived from
 * `audio/en/durations.json`. Renders one <Sequence> per scene.
 *
 * For the spike, scenes embed their narration <Audio> directly so the rendered
 * MP4 is self-contained. In production the render is silent and `assemble_en.sh`
 * muxes the global voiceover (matching the existing Manim flow).
 */

export const sceneSchema = z.object({
  component: z.string(),
  props: z.record(z.unknown()).default({}),
  durationInFrames: z.number().int().positive(),
  audio: z.string().optional(),
});

export const videoSchema = z.object({
  scenes: z.array(sceneSchema),
  embedAudio: z.boolean().default(false),
});

export type VideoProps = z.infer<typeof videoSchema>;

// `registry` is supplied in code by the per-job entry (palette + this job's
// Custom scenes); it is intentionally NOT part of the Zod input-props schema.
type MainCompositionProps = VideoProps & {
  registry?: Record<string, React.FC<Record<string, unknown>>>;
};

export const MainComposition: React.FC<MainCompositionProps> = ({ scenes, embedAudio, registry }) => {
  const components = registry ?? SCENE_COMPONENTS;
  let from = 0;
  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      {/* Persistent living background, BEHIND every scene. Each scene fades its
          own content in/out at its edges (fadeIn * fadeTail); during that dip
          this continuous background shows through, so scene-to-scene boundaries
          cross-dissolve instead of hard-cutting — and there is never a black or
          frozen frame between scenes (keeps freezedetect happy). No timeline
          overlap, so the per-segment voiceover stays perfectly in sync. */}
      <AmbientBackground />
      {scenes.map((scene, i) => {
        const Comp = components[scene.component];
        const start = from;
        from += scene.durationInFrames;
        if (!Comp) {
          return null;
        }
        return (
          <Sequence key={i} from={start} durationInFrames={scene.durationInFrames} name={scene.component}>
            {embedAudio && scene.audio ? <Audio src={staticFile(scene.audio)} /> : null}
            <Comp dur={scene.durationInFrames} {...scene.props} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
