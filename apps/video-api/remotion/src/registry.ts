import React from "react";
import {
  BulletScene,
  CodeScene,
  DiagramScene,
  FormulaScene,
  PlotScene,
  TitleScene,
} from "./scenes/data/scenes";

/**
 * Component registry: maps a stable component name (chosen by the blueprint) to
 * its React implementation. The data-driven STEM scenes below are the tested
 * palette a generated `video.json` composes. Per-job `Custom` scenes are merged
 * on top of this map by the generated per-job entry (src/entries/<id>.tsx).
 */
export const SCENE_COMPONENTS: Record<string, React.FC<Record<string, unknown>>> = {
  TitleScene: TitleScene as React.FC<Record<string, unknown>>,
  BulletScene: BulletScene as React.FC<Record<string, unknown>>,
  FormulaScene: FormulaScene as React.FC<Record<string, unknown>>,
  CodeScene: CodeScene as React.FC<Record<string, unknown>>,
  PlotScene: PlotScene as React.FC<Record<string, unknown>>,
  DiagramScene: DiagramScene as React.FC<Record<string, unknown>>,
};
