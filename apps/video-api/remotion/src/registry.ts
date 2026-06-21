import React from "react";
import {
  BarChartScene,
  BulletScene,
  CodeScene,
  ComparisonScene,
  CounterScene,
  DiagramScene,
  FlowScene,
  FormulaScene,
  FootageScene,
  ImageScene,
  LayeredSystemScene,
  MemoryScene,
  PlotScene,
  QuoteScene,
  SplitFocusScene,
  TerminalScene,
  TimelineScene,
  TitleScene,
  ZoomNarrativeScene,
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
  ComparisonScene: ComparisonScene as React.FC<Record<string, unknown>>,
  LayeredSystemScene: LayeredSystemScene as React.FC<Record<string, unknown>>,
  TimelineScene: TimelineScene as React.FC<Record<string, unknown>>,
  TerminalScene: TerminalScene as React.FC<Record<string, unknown>>,
  MemoryScene: MemoryScene as React.FC<Record<string, unknown>>,
  FlowScene: FlowScene as React.FC<Record<string, unknown>>,
  BarChartScene: BarChartScene as React.FC<Record<string, unknown>>,
  CounterScene: CounterScene as React.FC<Record<string, unknown>>,
  QuoteScene: QuoteScene as React.FC<Record<string, unknown>>,
  SplitFocusScene: SplitFocusScene as React.FC<Record<string, unknown>>,
  ZoomNarrativeScene: ZoomNarrativeScene as React.FC<Record<string, unknown>>,
  ImageScene: ImageScene as React.FC<Record<string, unknown>>,
  FootageScene: FootageScene as React.FC<Record<string, unknown>>,
};
