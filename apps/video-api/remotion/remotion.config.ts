import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setConcurrency(null);
// "swangle" = software ANGLE: works in headless Docker without a GPU and on
// macOS alike. Our scenes are DOM/SVG (KaTeX, Shiki, CSS), so no real GPU is
// needed; this avoids the "angle" renderer failing on GPU-less containers.
Config.setChromiumOpenGlRenderer("swangle");
