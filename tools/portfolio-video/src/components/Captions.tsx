import { useCurrentFrame, useVideoConfig } from "remotion";

import { COLORS, LAYOUT, SANS } from "../styles/theme";

export type Cue = { start: number; end: number; text: string };

/** Burned-in subtitles, timed from the synthesised narration. */
export const Captions = ({ cues }: { cues: Cue[] }) => {
  const seconds = useCurrentFrame() / useVideoConfig().fps;
  const cue = cues.find((c) => seconds >= c.start && seconds < c.end);
  if (!cue) return null;
  return (
    <div
      style={{
        position: "absolute",
        bottom: LAYOUT.captionBottom,
        left: 0,
        right: 0,
        display: "flex",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          background: "rgba(8,12,20,0.88)",
          borderRadius: 10,
          padding: "8px 22px",
          color: COLORS.white,
          fontFamily: SANS,
          fontSize: 30,
          fontWeight: 500,
          lineHeight: 1.35,
          textAlign: "center",
          whiteSpace: "pre",
        }}
      >
        {cue.text}
      </div>
    </div>
  );
};
