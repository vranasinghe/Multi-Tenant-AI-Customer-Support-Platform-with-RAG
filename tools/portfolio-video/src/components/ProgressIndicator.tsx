import { useCurrentFrame, useVideoConfig } from "remotion";

import { COLORS } from "../styles/theme";

/** A hairline along the bottom edge showing how far through the video the viewer is. */
export const ProgressIndicator = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        bottom: 0,
        height: 4,
        width: "100%",
        background: COLORS.line,
      }}
    >
      <div
        style={{
          height: 4,
          width: `${(frame / (durationInFrames - 1)) * 100}%`,
          background: COLORS.blue,
        }}
      />
    </div>
  );
};
