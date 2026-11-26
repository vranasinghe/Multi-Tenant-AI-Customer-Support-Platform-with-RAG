import script from "../data/generated/showcase-v2.json";
import { SHOWCASE_V2 } from "../scenes/showcase-v2/scenes";
import { TimedVideo, type VideoProps } from "./TimedVideo";

export const SHOWCASE_V2_FRAMES = script.frames;

export const PortfolioShowcaseV2 = (props: VideoProps) => (
  <TimedVideo script={script} scenes={SHOWCASE_V2} {...props} />
);
