import type { ComponentProps, ReactNode } from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";

import { progress } from "../../animations";
import { ApplicationWindow, TITLE_BAR } from "../../components/ApplicationWindow";
import { ScreenRecording } from "../../components/ScreenRecording";
import { COLORS, LAYOUT } from "../../styles/theme";

type Props = ComponentProps<typeof ScreenRecording> & {
  caption: string;
  fadeIn?: boolean;
  overlay?: ReactNode;
};

/** One centred application window with footage, dissolving in over the previous shot. */
export const FootageShot = ({ caption, fadeIn = false, overlay, ...recording }: Props) => {
  const frame = useCurrentFrame();
  const outer = recording.height + TITLE_BAR;
  const top = LAYOUT.contentTop + Math.max(0, (780 - outer) / 2);
  return (
    <AbsoluteFill
      style={{
        opacity: fadeIn ? progress(frame, 0, 8) : 1,
        backgroundColor: fadeIn ? COLORS.background : undefined,
      }}
    >
      <div style={{ position: "absolute", top, left: (1920 - recording.width) / 2 }}>
        <ApplicationWindow width={recording.width} height={recording.height} caption={caption}>
          <ScreenRecording {...recording} />
          {overlay}
        </ApplicationWindow>
      </div>
    </AbsoluteFill>
  );
};
