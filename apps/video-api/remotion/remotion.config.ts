import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setConcurrency(null);
// No OpenGL renderer is forced: Chrome decides. Without a GPU (the worker
// container) it then composites and rasterizes on the CPU with Skia, keeping
// SwiftShader for WebGL only (`--use-angle=swiftshader-webgl`). Our scenes are
// DOM/SVG (KaTeX, Shiki, CSS), no WebGL, which is the case the Remotion docs
// give the default renderer for. Forcing "swangle" instead routes every frame's
// compositing and raster through SwiftShader: measured on a real 12-scene job,
// 3x slower and 4x more CPU time for the same image (SSIM 0.997+).
