import { AbsoluteFill, useCurrentFrame } from "remotion";

import { progress } from "../animations";
import { COLORS, SANS } from "../styles/theme";
import { ApplicationWindow, TITLE_BAR } from "./ApplicationWindow";
import { ScreenRecording, type Crop, type Highlight, type Segment } from "./ScreenRecording";

export type BigScreenProps = {
  clip: string;
  caption: string;
  segments: Segment[];
  /** Camera move across the whole shot: from `crop` to `to`. */
  crop: Crop;
  to?: Crop;
  moveAt?: number;
  moveFrames?: number;
  width?: number;
  height?: number;
  label?: string;
  /** Move the label when the bottom corner holds what the shot is about. */
  labelAt?: "bottom" | "top";
  highlights?: Highlight[];
  fadeIn?: boolean;
};

export const SCREEN_TOP = 88;

/** One application screen at a time, as large as the frame allows, with a slow camera move. */
export const BigScreen = ({
  clip,
  caption,
  segments,
  crop,
  to,
  moveAt = 0,
  moveFrames,
  width = 1440,
  height = 810,
  label,
  labelAt = "bottom",
  highlights,
  fadeIn = true,
}: BigScreenProps) => {
  const frame = useCurrentFrame();
  const length = segments.reduce((sum, segment) => sum + segment.frames, 0);
  const top = SCREEN_TOP + Math.max(0, (846 - (height + TITLE_BAR)) / 2);
  return (
    <AbsoluteFill
      style={{ opacity: fadeIn ? progress(frame, 0, 9) : 1, backgroundColor: COLORS.background }}
    >
      <div style={{ position: "absolute", top, left: (1920 - width) / 2 }}>
        <ApplicationWindow width={width} height={height} caption={caption}>
          <ScreenRecording
            clip={clip}
            segments={segments}
            width={width}
            height={height}
            crop={crop}
            zoomTo={to}
            zoomAt={moveAt}
            zoomFrames={moveFrames ?? length}
            highlights={highlights}
          />
          {label ? (
            <div
              style={{
                position: "absolute",
                ...(labelAt === "top" ? { right: 20, top: 16 } : { left: 20, bottom: 20 }),
                padding: "10px 20px",
                borderRadius: 10,
                background: "rgba(8,12,20,0.92)",
                borderLeft: `5px solid ${COLORS.blue}`,
                color: COLORS.white,
                fontFamily: SANS,
                fontSize: 28,
                fontWeight: 700,
              }}
            >
              {label}
            </div>
          ) : null}
        </ApplicationWindow>
      </div>
    </AbsoluteFill>
  );
};
