import React, { useEffect, useState } from "react";
import { continueRender, delayRender, interpolate, useCurrentFrame } from "remotion";
import katex from "katex";
import "katex/dist/katex.min.css";
import { colors, fonts } from "../style/tokens";

/**
 * LaTeX math rendered with KaTeX — the universal STEM primitive. Works for any
 * field: calculus, linear algebra, physics, chemistry, statistics, logic.
 * Renders synchronously to HTML; the render is held only until KaTeX web fonts
 * are ready, so equations never flash unstyled.
 *
 *   <MathFormula tex="\\int_a^b f(x)\\,dx = F(b) - F(a)" />
 *   <MathFormula tex="\\vec{F} = m\\vec{a}" display color={colors.kernel} />
 */
export const MathFormula: React.FC<{
  tex: string;
  display?: boolean;
  fontSize?: number;
  color?: string;
  delay?: number; // frames; fades/scales in
  align?: "left" | "center";
}> = ({ tex, display = true, fontSize = 46, color = colors.text, delay = 0, align = "center" }) => {
  const frame = useCurrentFrame();
  const [handle] = useState(() => delayRender("katex-fonts"));

  useEffect(() => {
    let cancelled = false;
    const ready = (document as Document & { fonts?: { ready: Promise<unknown> } }).fonts?.ready;
    if (ready) {
      ready.then(() => !cancelled && continueRender(handle)).catch(() => continueRender(handle));
    } else {
      continueRender(handle);
    }
    return () => {
      cancelled = true;
    };
  }, [handle]);

  const html = katex.renderToString(tex, { displayMode: display, throwOnError: false });
  const p = interpolate(frame - delay, [0, 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <div
      style={{
        color,
        fontSize,
        fontFamily: fonts.sans,
        opacity: p,
        transform: `translateY(${interpolate(p, [0, 1], [16, 0])}px)`,
        textAlign: align,
        // KaTeX inherits color from currentColor for most glyphs
      }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
};
