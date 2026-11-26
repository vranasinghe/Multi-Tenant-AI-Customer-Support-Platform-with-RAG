import { AbsoluteFill, useCurrentFrame } from "remotion";

import { progress } from "../animations";
import script from "../data/generated/documentary.json";
import { DOCUMENTARY } from "../scenes/documentary";
import { COLORS, SANS } from "../styles/theme";
import { TimedVideo, type Script, type VideoProps } from "./TimedVideo";

export const DOCUMENTARY_FRAMES = script.frames;

const CARD = 48;

/** Where the viewer is: a short card when a chapter opens, then a small marker at the top. */
const Chapters = () => {
  const frame = useCurrentFrame();
  const segments = (script as Script).segments;
  const current = [...segments].reverse().find((segment) => frame >= segment.from)!;
  const opening = segments.find((segment) => segment.chapter === current.chapter)!;
  const local = frame - opening.from;
  // The film opens on its own title and ends on its end card.
  const framed = current.chapter > 1 && current.chapter < 10;
  if (framed && local < CARD) {
    return (
      <AbsoluteFill
        style={{
          background: COLORS.background,
          opacity: 1 - progress(local, CARD - 10, 10),
          alignItems: "center",
          justifyContent: "center",
          paddingBottom: 100,
          fontFamily: SANS,
        }}
      >
        <div style={{ color: COLORS.accent, fontSize: 30, fontWeight: 700, letterSpacing: 4 }}>
          CHAPTER {current.chapter}
        </div>
        <div style={{ color: COLORS.white, fontSize: 64, fontWeight: 700, marginTop: 18 }}>
          {current.chapterTitle}
        </div>
      </AbsoluteFill>
    );
  }
  if (!framed) return null;
  return (
    <div
      style={{
        position: "absolute",
        top: 76,
        right: 48,
        color: COLORS.muted,
        fontFamily: SANS,
        fontSize: 16,
        letterSpacing: 0.5,
      }}
    >
      Chapter {current.chapter} · {current.chapterTitle}
    </div>
  );
};

export const EngineeringDocumentary = (props: VideoProps) => (
  <TimedVideo {...props} script={script as Script} scenes={DOCUMENTARY} overlay={Chapters} />
);
