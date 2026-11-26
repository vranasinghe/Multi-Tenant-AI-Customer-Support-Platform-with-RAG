// Video A timing, from docs/portfolio-video/02_CINEMATIC_TRAILER_SCRIPT.md.
// To fit a recorded voice-over, change `seconds` here and re-time the subtitles.
import { FPS } from "../styles/theme";

export const SHOWCASE_SCENES = [
  { id: "A1", name: "Hook", seconds: 10 },
  { id: "A2", name: "Product", seconds: 13 },
  { id: "A3", name: "It works", seconds: 20 },
  { id: "A4", name: "Underneath", seconds: 14 },
  { id: "A5", name: "Evidence", seconds: 15 },
  { id: "A6", name: "Close", seconds: 8 },
] as const;

export type SceneId = (typeof SHOWCASE_SCENES)[number]["id"];

export const showcaseTimeline = SHOWCASE_SCENES.reduce<
  { id: SceneId; name: string; from: number; frames: number }[]
>((list, scene) => {
  const previous = list[list.length - 1];
  const from = previous ? previous.from + previous.frames : 0;
  return [...list, { id: scene.id, name: scene.name, from, frames: scene.seconds * FPS }];
}, []);

export const SHOWCASE_FRAMES = showcaseTimeline.reduce((sum, scene) => sum + scene.frames, 0);

/** Interface sound cues (used only if public/audio/click.wav exists). */
export const SHOWCASE_CLICKS = [
  0, 15, 30, 45, 690, 900, 1080, 1710, 1718, 1726, 1734, 1742, 1750, 1758,
];
