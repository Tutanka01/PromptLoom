---
name: remotion-skill
description: How to author Remotion video scenes for video-api (official Remotion LLM guidance + project pedagogical rules)
---

# About Remotion

Remotion is a framework that can create videos programmatically.
It is based on React.js. All output should be valid React code and be written in TypeScript.

# Project structure

A Remotion Project consists of an entry file, a Root file and any number of React component files.
A project can be scaffolded using the "npx create-video@latest --blank" command.
The entry file is usually named "src/index.ts" and looks like this:

```ts
import {registerRoot} from 'remotion';
import {Root} from './Root';

registerRoot(Root);
```

The Root file is usually named "src/Root.tsx" and looks like this:

```tsx
import {Composition} from 'remotion';
import {MyComp} from './MyComp';

export const Root: React.FC = () => {
	return (
		<>
			<Composition
				id="MyComp"
				component={MyComp}
				durationInFrames={120}
				width={1920}
				height={1080}
				fps={30}
				defaultProps={{}}
			/>
		</>
	);
};
```

A `<Composition>` defines a video that can be rendered. It consists of a React "component", an "id", a "durationInFrames", a "width", a "height" and a frame rate "fps".
The default frame rate should be 30.
The default height should be 1080 and the default width should be 1920.
The default "id" should be "MyComp".
The "defaultProps" must be in the shape of the React props the "component" expects.

Inside a React "component", one can use the "useCurrentFrame()" hook to get the current frame number.
Frame numbers start at 0.

```tsx
export const MyComp: React.FC = () => {
	const frame = useCurrentFrame();
	return <div>Frame {frame}</div>;
};
```

# Component Rules

Inside a component, regular HTML and SVG tags can be returned.
There are special tags for video and audio.
Those special tags accept regular CSS styles.

If a video is included in the component it should use the "<Video>" tag.

```tsx
import {Video} from '@remotion/media';

export const MyComp: React.FC = () => {
	return (
		<div>
			<Video
				src="https://remotion.dev/bbb.mp4"
				style={{width: '100%'}}
			/>
		</div>
	);
};
```

Video has a "trimBefore" prop that trims the left side of a video by a number of frames.
Video has a "trimAfter" prop that limits how long a video is shown.
Video has a "volume" prop that sets the volume of the video. It accepts values between 0 and 1.

If an non-animated image is included In the component it should use the "<Img>" tag.

```tsx
import {Img} from 'remotion';

export const MyComp: React.FC = () => {
	return <Img src="https://remotion.dev/logo.png" style={{width: '100%'}} />;
};
```

If an animated GIF is included, the "@remotion/gif" package should be installed and the "<Gif>" tag should be used.

```tsx
import {Gif} from '@remotion/gif';

export const MyComp: React.FC = () => {
	return (
		<Gif
			src="https://media.giphy.com/media/l0MYd5y8e1t0m/giphy.gif"
			style={{width: '100%'}}
		/>
	);
};
```

If audio is included, the "<Audio>" tag should be used.

```tsx
import {Audio} from '@remotion/media';

export const MyComp: React.FC = () => {
	return <Audio src="https://remotion.dev/audio.mp3" />;
};
```

Asset sources can be specified as either a Remote URL or an asset that is referenced from the "public/" folder of the project.
If an asset is referenced from the "public/" folder, it should be specified using the "staticFile" API from Remotion

```tsx
import {staticFile} from 'remotion';
import {Audio} from '@remotion/media';

export const MyComp: React.FC = () => {
	return <Audio src={staticFile('audio.mp3')} />;
};
```

Audio has a "trimBefore" prop that trims the left side of a audio by a number of frames.
Audio has a "trimAfter" prop that limits how long a audio is shown.
Audio has a "volume" prop that sets the volume of the audio. It accepts values between 0 and 1.

If two elements should be rendered on top of each other, they should be layered using the "AbsoluteFill" component from "remotion".

```tsx
import {AbsoluteFill} from 'remotion';

export const MyComp: React.FC = () => {
	return (
		<AbsoluteFill>
			<AbsoluteFill style={{background: 'blue'}}>
				<div>This is in the back</div>
			</AbsoluteFill>
			<AbsoluteFill style={{background: 'blue'}}>
				<div>This is in front</div>
			</AbsoluteFill>
		</AbsoluteFill>
	);
};
```

Any Element can be wrapped in a "Sequence" component from "remotion" to place the element later in the video.

```tsx
import {Sequence} from 'remotion';

export const MyComp: React.FC = () => {
	return (
		<Sequence from={10} durationInFrames={20}>
			<div>This only appears after 10 frames</div>
		</Sequence>
	);
};
```

A Sequence has a "from" prop that specifies the frame number where the element should appear.
The "from" prop can be negative, in which case the Sequence will start immediately but cut off the first "from" frames.

A Sequence has a "durationInFrames" prop that specifies how long the element should appear.

If a child component of Sequence calls "useCurrentFrame()", the enumeration starts from the first frame the Sequence appears and starts at 0.

```tsx
import {Sequence} from 'remotion';

export const Child: React.FC = () => {
	const frame = useCurrentFrame();

	return <div>At frame 10, this should be 0: {frame}</div>;
};

export const MyComp: React.FC = () => {
	return (
		<Sequence from={10} durationInFrames={20}>
			<Child />
		</Sequence>
	);
};
```

For displaying multiple elements after another, the "Series" component from "remotion" can be used.

```tsx
import {Series} from 'remotion';

export const MyComp: React.FC = () => {
	return (
		<Series>
			<Series.Sequence durationInFrames={20}>
				<div>This only appears immediately</div>
			</Series.Sequence>
			<Series.Sequence durationInFrames={30}>
				<div>This only appears after 20 frames</div>
			</Series.Sequence>
			<Series.Sequence durationInFrames={30} offset={-8}>
				<div>This only appears after 42 frames</div>
			</Series.Sequence>
		</Series>
	);
};
```

The "Series.Sequence" component works like "Sequence", but has no "from" prop.
Instead, it has a "offset" prop shifts the start by a number of frames.

For displaying multiple elements after another another and having a transition inbetween, the "TransitionSeries" component from "@remotion/transitions" can be used.

```tsx
import {
	linearTiming,
	springTiming,
	TransitionSeries,
} from '@remotion/transitions';

import {fade} from '@remotion/transitions/fade';
import {wipe} from '@remotion/transitions/wipe';

export const MyComp: React.FC = () => {
	return (
		<TransitionSeries>
			<TransitionSeries.Sequence durationInFrames={60}>
				<Fill color="blue" />
			</TransitionSeries.Sequence>
			<TransitionSeries.Transition
				timing={springTiming({config: {damping: 200}})}
				presentation={fade()}
			/>
			<TransitionSeries.Sequence durationInFrames={60}>
				<Fill color="black" />
			</TransitionSeries.Sequence>
			<TransitionSeries.Transition
				timing={linearTiming({durationInFrames: 30})}
				presentation={wipe()}
			/>
			<TransitionSeries.Sequence durationInFrames={60}>
				<Fill color="white" />
			</TransitionSeries.Sequence>
		</TransitionSeries>
	);
};
```

"TransitionSeries.Sequence" works like "Series.Sequence" but has no "offset" prop.
The order of tags is important, "TransitionSeries.Transition" must be inbetween "TransitionSeries.Sequence" tags.

Remotion needs all of the React code to be deterministic. Therefore, it is forbidden to use the Math.random() API.
If randomness is requested, the "random()" function from "remotion" should be used and a static seed should be passed to it.
The random function returns a number between 0 and 1.

```tsx twoslash
import {random} from 'remotion';

export const MyComp: React.FC = () => {
	return <div>Random number: {random('my-seed')}</div>;
};
```

Remotion includes an interpolate() helper that can animate values over time.

```tsx
import {interpolate} from 'remotion';

export const MyComp: React.FC = () => {
	const frame = useCurrentFrame();
	const value = interpolate(frame, [0, 100], [0, 1], {
		extrapolateLeft: 'clamp',
		extrapolateRight: 'clamp',
	});
	return (
		<div>
			Frame {frame}: {value}
		</div>
	);
};
```

The "interpolate()" function accepts a number and two arrays of numbers.
The first argument is the value to animate.
The first array is the input range, the second array is the output range.
The fourth argument is optional but code should add "extrapolateLeft: 'clamp'" and "extrapolateRight: 'clamp'" by default.
The function returns a number between the first and second array.

If the "fps", "durationInFrames", "height" or "width" of the composition are required, the "useVideoConfig()" hook from "remotion" should be used.

```tsx
import {useVideoConfig} from 'remotion';

export const MyComp: React.FC = () => {
	const {fps, durationInFrames, height, width} = useVideoConfig();
	return (
		<div>
			fps: {fps}
			durationInFrames: {durationInFrames}
			height: {height}
			width: {width}
		</div>
	);
};
```

Remotion includes a "spring()" helper for spring-based motion. By default it animates from 0 to 1; the duration is not fixed in advance.

```tsx
import {spring} from 'remotion';

export const MyComp: React.FC = () => {
	const frame = useCurrentFrame();
	const {fps} = useVideoConfig();

	const value = spring({
		fps,
		frame,
		config: {
			damping: 200,
		},
	});
	return (
		<div>
			Frame {frame}: {value}
		</div>
	);
};
```

## Rendering

To render a video, the CLI command "npx remotion render [id]" can be used.
The composition "id" should be passed, for example:

$ npx remotion render MyComp

To render a still image, the CLI command "npx remotion still [id]" can be used.
For example:

$ npx remotion still MyComp

## Rendering on Lambda

Videos can be rendered in the cloud using AWS Lambda.
The setup described under https://www.remotion.dev/docs/lambda/setup must be completed.

Rendering requires a Lambda function and a site deployed on S3.

If the user is using the CLI:

- A Lambda function can be deployed using `npx remotion lambda functions deploy`: https://www.remotion.dev/docs/lambda/cli/functions/deploy
- A site can be deployed using `npx remotion lambda sites create`: https://www.remotion.dev/docs/lambda/cli/sites/create. The first argument must refer to the entry point.
- A video can be rendered using `npx remotion lambda render [comp-id]`. The composition ID must be referenced.

If the user is using the Node.js APIs:

- A Lambda function can be deployed using `deployFunction()`: https://www.remotion.dev/docs/lambda/deployfunction
- A site can be deployed using `deploySite()`: https://www.remotion.dev/docs/lambda/deploysite
- A video can be rendered using `renderMediaOnLambda()`: https://www.remotion.dev/docs/lambda/rendermediaonlambda.
- If a video is rendered, the progress must be polled using `getRenderProgress()`: https://www.remotion.dev/docs/lambda/getrenderprogress

---

# House rules for video-api (pedagogical STEM videos — any subject)

The section above is Remotion's own LLM guidance (downloaded from
https://www.remotion.dev/llms.txt). The rules below are specific to THIS
project. When you author a scene, follow both.

This project makes explainer videos for **any STEM topic** — mathematics,
physics, chemistry, biology, statistics, computer science, engineering. The
component library is domain-agnostic. A topic like the Linux kernel is just one
subject among many; never assume the domain.

## Goal: teach, don't decorate

Each scene must make ONE idea click. The narration is the spine; the visuals
exist to make the spoken sentence concrete. If the voice says "the integral is
the area under the curve", the screen shows a shaded area under a plotted curve.
If it says "syscall table", it shows a table of syscall numbers. Pick the visual
that matches the sentence — never a generic row of cards.

## Choose the right primitive for the subject

- **Math / equations** (any field): `<MathFormula tex="…" />` (KaTeX).
- **Functions, data, physics over time**: `<Plot fn={…} … />` (axes, animated
  curve, tangent, area, moving point).
- **Code / algorithms**: `<CodeBlock lang="…" />` (Shiki, line-by-line reveal).
- **Systems, processes, relationships**: `Card` + `Arrow` + `Zone` nodes/edges.
- **Quantities / comparison**: bars/pills, counters.
Compose these; they cover most STEM explanations.

## Mandatory techniques

1. **Living background.** Never put content on a static fill. Use
   `<AmbientBackground />` (continuous slow motion). A near-static frame trips
   `freezedetect` and looks dead — the #1 defect of the old Manim pipeline.
2. **Progressive disclosure.** Reveal one element at a time and REMOVE what is
   no longer needed. Don't pile everything on screen. Density kills
   comprehension.
3. **Motion with meaning.** Use `spring()` for entrances and for movement that
   represents something (a point sweeping a curve, a token travelling). Avoid
   decorative motion.
4. **Focus / dim.** Dim (opacity ~0.32) everything except the element under
   discussion; add a soft glow to the focus. No permanent highlight on all.
5. **Scene transitions.** Join scenes with `@remotion/transitions`
   (`TransitionSeries` + `fade`/`slide`/`wipe`), not hard cuts.

## Synchronisation contract (REQUIRED)

A scene receives its duration from `useVideoConfig().durationInFrames`. Drive
every beat off normalized progress `p = frame / durationInFrames` (or off
`spring`/`interpolate` on `frame`). Aim for 5–7 beats; keep the image evolving
until ~85–90% of the scene, then a short settle. Never end on a long static
hold. Durations come from `audio/en/durations.json` — never hardcode seconds.

## Layout discipline

- **Space things out.** Nodes in a flow/row need clear gaps so connectors are
  visible and nothing overlaps. Crowding is a real bug we hit.
- **Never let a moving element cover a label.** Route a travelling token ABOVE
  or BELOW the row it describes, with a thin pointer to the active node.
- **Keep text in the safe zone** (≥10% margin). Max ~7 words per line. Leave
  text up long enough to read it twice.

## Pitfalls (do not repeat)

- A correct duration with a frozen image is still a failure. Keep motion.
- `interpolate()` input ranges must be STRICTLY increasing (no `[0.5, 0.5, …]`).
- Async resources (Shiki, KaTeX fonts, images) must hold the render with
  `delayRender()` / `continueRender()` — see `<CodeBlock>` and `<MathFormula>`.
- Use web-safe fonts available on the Linux worker (Inter, JetBrains Mono /
  DejaVu), never macOS-only fonts.

## What you may import

`react`, `remotion`, `@remotion/transitions`, `@remotion/shapes`, `shiki`,
`katex`, and the project library: `src/components/primitives` and
`src/catalog/*` (see `remotion-catalog.md` for the full proposable palette). Do
NOT import `fs`, `child_process`, `eval`, network clients, or anything else.
