import React from "react";
import { Composition } from "remotion";
import { MainComposition, videoSchema } from "./MainComposition";

/**
 * Studio / default entry. Production renders use a generated per-job entry
 * (src/entries/<id>.tsx) that augments the registry with that job's Custom
 * scenes; this Root registers the same data-driven `Video` composition with the
 * palette only, for `npm run dev` and as a typecheck target.
 */
export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Video"
      component={MainComposition}
      schema={videoSchema}
      defaultProps={{ scenes: [], embedAudio: false, captionMode: "off", subtitles: [], transitionProfile: "minimal" }}
      fps={60}
      width={1920}
      height={1080}
      durationInFrames={60}
      calculateMetadata={({ props }) => ({
        durationInFrames: Math.max(
          1,
          props.scenes.reduce((s, sc) => s + sc.durationInFrames, 0)
        ),
      })}
    />
  );
};
