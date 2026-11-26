import type { FC } from "react";

import type { SceneProps } from "../../compositions/TimedVideo";
import * as architecture from "./architecture";
import { challengeScenes, ProblemList } from "./challenges";
import * as closing from "./closing";
import * as demo from "./demo";
import { Opening, Problem } from "./intro";
import * as method from "./method";
import * as security from "./security";

/** Segment ids come from docs/portfolio-video/14_NARRATION_V2.md. */
export const DOCUMENTARY: Record<string, FC<SceneProps>> = {
  "1a": Opening,
  "1b": Problem,
  "2a": demo.SetUp,
  "2b": demo.Ask,
  "2c": demo.Customers,
  "3a": architecture.Experience,
  "3b": architecture.Application,
  "3c": architecture.Data,
  "3d": architecture.Intelligence,
  "3e": architecture.Whole,
  "4a": architecture.Vectors,
  "4b": architecture.Search,
  "4c": architecture.NotEstablished,
  "5a": security.TwoBusinesses,
  "5b": security.Layers,
  "5c": security.PublicBoundaries,
  "6.0": ProblemList,
  ...challengeScenes,
  "7a": method.Method,
  "7b": method.Results,
  "7c": method.Failures,
  "7d": method.Capacity,
  "7e": method.SelfAudit,
  "8a": closing.Contribution,
  "9a": closing.WhereItStands,
  "10a": closing.Close,
};
