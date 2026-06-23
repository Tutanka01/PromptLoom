import React, { useEffect, useState } from "react";
import { continueRender, delayRender, interpolate, useCurrentFrame } from "remotion";
import type { ThemedToken } from "shiki";
import { createHighlighter, type Highlighter } from "shiki";
import { alpha, colors, fonts } from "../style/tokens";

/**
 * Real syntax-highlighted, progressively-revealed code — the single biggest
 * pedagogical lever for low-level/kernel content (C, syscalls, bash). Uses
 * Shiki for accurate highlighting; the highlighter is loaded once and the
 * render is held via delayRender() until tokens are ready (the standard
 * Remotion pattern for async resources).
 *
 * Lines reveal one by one (slide + fade), so the viewer reads with the
 * narration instead of being shown a wall of code.
 */

let highlighterPromise: Promise<Highlighter> | null = null;
const getHighlighter = (): Promise<Highlighter> => {
  if (!highlighterPromise) {
    highlighterPromise = createHighlighter({
      themes: ["github-dark"],
      langs: ["c", "bash", "tsx", "python", "json"],
    });
  }
  return highlighterPromise;
};

export const CodeBlock: React.FC<{
  code: string;
  lang?: string;
  fontSize?: number;
  lineReveal?: number; // frames between each line appearing
  startAt?: number; // frame at which the first line appears
  accent?: string;
  title?: string;
}> = ({ code, lang = "c", fontSize = 30, lineReveal = 6, startAt = 0, accent = colors.user, title }) => {
  const frame = useCurrentFrame();
  const [lines, setLines] = useState<ThemedToken[][] | null>(null);
  const [handle] = useState(() => delayRender(`shiki-${lang}`));

  useEffect(() => {
    let active = true;
    getHighlighter()
      .then((h) => {
        if (!active) return;
        const { tokens } = h.codeToTokens(code.replace(/\n+$/, ""), {
          lang: lang as never,
          theme: "github-dark",
        });
        setLines(tokens);
        continueRender(handle);
      })
      .catch(() => continueRender(handle));
    return () => {
      active = false;
    };
  }, [code, lang, handle]);

  return (
    <div
      style={{
        background: "#0E1420",
        border: `1.5px solid ${alpha(accent, 0.33)}`,
        borderRadius: 16,
        boxShadow: `0 22px 60px rgba(0,0,0,0.55), 0 0 0 1px ${alpha(accent, 0.13)}`,
        padding: "26px 30px",
        fontFamily: fonts.mono,
        fontSize,
        lineHeight: 1.55,
        minWidth: 520,
      }}
    >
      {/* window chrome / optional file title */}
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 16 }}>
        <span style={{ width: 13, height: 13, borderRadius: "50%", background: "#FB5C6B" }} />
        <span style={{ width: 13, height: 13, borderRadius: "50%", background: "#FFBE0B" }} />
        <span style={{ width: 13, height: 13, borderRadius: "50%", background: "#06D6A0" }} />
        {title && (
          <span style={{ marginLeft: 12, color: colors.muted, fontSize: fontSize * 0.62, fontFamily: fonts.sans }}>
            {title}
          </span>
        )}
      </div>
      {(lines ?? []).map((line, i) => {
        const lineStart = startAt + i * lineReveal;
        const p = interpolate(frame - lineStart, [0, 10], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        return (
          <div
            key={i}
            style={{
              opacity: p,
              transform: `translateX(${interpolate(p, [0, 1], [14, 0])}px)`,
              whiteSpace: "pre",
              minHeight: fontSize * 1.55,
            }}
          >
            {line.length === 0 ? " " : line.map((tok, j) => (
              <span key={j} style={{ color: tok.color ?? colors.text }}>
                {tok.content}
              </span>
            ))}
          </div>
        );
      })}
    </div>
  );
};
