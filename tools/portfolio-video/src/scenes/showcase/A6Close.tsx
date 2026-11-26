import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";

import { progress } from "../../animations";
import { EndCard } from "../../components/EndCard";
import { COLORS } from "../../styles/theme";

export const A6Close = ({ frames }: { frames?: number }) => {
  const frame = useCurrentFrame();
  const config = useVideoConfig();
  const total = frames ?? config.durationInFrames;
  const fadeIn = progress(frame, 0, 8);
  return (
    <AbsoluteFill style={{ opacity: fadeIn, backgroundColor: COLORS.background }}>
      <EndCard />
      {/* Fade to the brand background on the last 12 frames. */}
      <AbsoluteFill
        style={{ backgroundColor: COLORS.background, opacity: progress(frame, total - 12, 11) }}
      />
    </AbsoluteFill>
  );
};
