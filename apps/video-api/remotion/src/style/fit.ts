import { fonts } from "./tokens";

/**
 * Text fitting for fixed boxes. Labels are written by an LLM, so their length
 * is unknown when a layout is designed: a component that gives a label a fixed
 * font size inside a fixed box eventually overflows it or runs into its
 * neighbour. Components size such text with `fitText` instead — the largest
 * font size (within bounds) at which the text wraps into the box.
 *
 * Widths are measured with a canvas in the same Chromium that renders the
 * frame, with the same font stack as the DOM, so the prediction matches the
 * layout. Results are memoised: pure, deterministic and cheap per frame.
 */

let context: CanvasRenderingContext2D | null | undefined;
const widths = new Map<string, number>();

const canvas = (): CanvasRenderingContext2D | null => {
  if (context === undefined) {
    context = typeof document === "undefined" ? null : document.createElement("canvas").getContext("2d");
  }
  return context;
};

/** Width in px of `text` on a single line. */
export const measureText = (text: string, fontSize: number, weight = 600, family: string = fonts.sans): number => {
  const key = `${weight}|${fontSize}|${family}|${text}`;
  const cached = widths.get(key);
  if (cached !== undefined) return cached;
  const ctx = canvas();
  let width: number;
  if (ctx) {
    ctx.font = `${weight} ${fontSize}px ${family}`;
    width = ctx.measureText(text).width;
  } else {
    width = text.length * fontSize * 0.56; // no canvas (never in Chromium): average glyph
  }
  widths.set(key, width);
  return width;
};

/** Greedy word wrap, as the browser does it: the lines and their widths. */
export const wrapText = (
  text: string,
  fontSize: number,
  maxWidth: number,
  weight = 600,
  family: string = fonts.sans,
): { lines: string[]; widest: number } => {
  const words = text.split(/\s+/).filter(Boolean);
  const space = measureText(" ", fontSize, weight, family);
  const lines: string[] = [];
  let line = "";
  let lineW = 0;
  let widest = 0;
  for (const word of words) {
    const w = measureText(word, fontSize, weight, family);
    if (!line) {
      line = word;
      lineW = w;
    } else if (lineW + space + w > maxWidth) {
      lines.push(line);
      widest = Math.max(widest, lineW);
      line = word;
      lineW = w;
    } else {
      line = `${line} ${word}`;
      lineW += space + w;
    }
  }
  if (line) {
    lines.push(line);
    widest = Math.max(widest, lineW);
  }
  return { lines: lines.length ? lines : [""], widest };
};

export type FitOptions = {
  /** Box width in px. */
  width: number;
  /** Optional box height in px (lines x fontSize x lineHeight must fit). */
  height?: number;
  maxLines?: number;
  max: number;
  min?: number;
  weight?: number;
  family?: string;
  lineHeight?: number;
};

export type Fit = {
  fontSize: number;
  lines: number;
  /** Widest line at that size, px — to size a box to its content. */
  width: number;
  /** False when even `min` does not fit (the text will wrap/clip at `min`). */
  fits: boolean;
};

// Kerning and sub-pixel rounding differ slightly between canvas and DOM text.
const SAFETY = 0.96;

/** Largest font size in [min, max] at which `text` fits the box. */
export const fitText = (text: string, opts: FitOptions): Fit => {
  const { width, height, maxLines = 1, max, weight = 600, family = fonts.sans, lineHeight = 1.18 } = opts;
  const min = Math.min(opts.min ?? Math.round(max * 0.6), max);
  const room = Math.max(1, width * SAFETY);
  let last: Fit = { fontSize: min, lines: 1, width: 0, fits: false };
  for (let size = Math.floor(max); size >= min; size -= 1) {
    const { lines, widest } = wrapText(text, size, room, weight, family);
    const fitsHeight = height === undefined || lines.length * size * lineHeight <= height;
    last = { fontSize: size, lines: lines.length, width: widest, fits: false };
    if (lines.length <= maxLines && widest <= room && fitsHeight) {
      return { ...last, fits: true };
    }
  }
  return last;
};

/** One font size for a set of labels that must look alike (chips, axis labels):
 * the smallest of their individual fits. */
export const fitTogether = (texts: string[], opts: FitOptions): Fit => {
  let out: Fit = { fontSize: opts.max, lines: 1, width: 0, fits: true };
  for (const text of texts) {
    const fit = fitText(text, opts);
    if (fit.fontSize < out.fontSize) out = { ...out, fontSize: fit.fontSize };
    out = { ...out, fits: out.fits && fit.fits };
  }
  let lines = 1;
  let widest = 0;
  for (const text of texts) {
    const wrapped = wrapText(text, out.fontSize, opts.width * SAFETY, opts.weight ?? 600, opts.family ?? fonts.sans);
    lines = Math.max(lines, wrapped.lines.length);
    widest = Math.max(widest, wrapped.widest);
  }
  return { ...out, lines, width: widest };
};
