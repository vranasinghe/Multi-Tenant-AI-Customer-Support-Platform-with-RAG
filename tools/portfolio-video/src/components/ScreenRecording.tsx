import { Freeze, OffthreadVideo, Sequence, staticFile, useCurrentFrame } from "remotion";

import { mix, progress } from "../animations";
import { COLORS, FPS } from "../styles/theme";

/** A region of the 1920×1080 recording. Its height follows the window's aspect ratio. */
export type Crop = { x: number; y: number; w: number };

export type Segment = {
  /** Second in the recording where this segment starts. */
  from: number;
  /** Length on the timeline, in frames. */
  frames: number;
  /** Playback speed; 0 holds the frame at `from`. */
  rate: number;
};

export type Highlight = { x: number; y: number; w: number; h: number; at: number; until?: number };

type Props = {
  clip: string;
  segments: Segment[];
  width: number;
  height: number;
  /** Start region, and optionally where the camera moves to. */
  crop: Crop;
  zoomTo?: Crop;
  zoomAt?: number;
  zoomFrames?: number;
  highlights?: Highlight[];
};

export const ScreenRecording = ({
  clip,
  segments,
  width,
  height,
  crop,
  zoomTo,
  zoomAt = 0,
  zoomFrames = 18,
  highlights = [],
}: Props) => {
  const frame = useCurrentFrame();
  const t = zoomTo ? progress(frame, zoomAt, zoomFrames) : 0;
  const view = zoomTo
    ? { x: mix(crop.x, zoomTo.x, t), y: mix(crop.y, zoomTo.y, t), w: mix(crop.w, zoomTo.w, t) }
    : crop;
  const scale = width / view.w;
  const video = (from: number, rate: number) => (
    <OffthreadVideo
      muted
      src={staticFile(`footage/${clip}.mp4`)}
      trimBefore={Math.round(from * FPS)}
      playbackRate={rate || 1}
      style={{
        position: "absolute",
        width: 1920 * scale,
        height: 1080 * scale,
        left: -view.x * scale,
        top: -view.y * scale,
        maxWidth: "none",
      }}
    />
  );

  let start = 0;
  return (
    <div style={{ position: "relative", width, height, overflow: "hidden", background: "#F8FAFC" }}>
      {segments.map((segment, index) => {
        const from = start;
        start += segment.frames;
        const last = index === segments.length - 1;
        return (
          <Sequence
            key={`${segment.from}-${index}`}
            from={from}
            // The last segment also covers the cross-dissolve into the next scene.
            durationInFrames={last ? segment.frames + 15 : segment.frames}
            layout="none"
          >
            {segment.rate === 0 ? (
              <Freeze frame={0}>{video(segment.from, 1)}</Freeze>
            ) : (
              video(segment.from, segment.rate)
            )}
          </Sequence>
        );
      })}
      {highlights.map((h) => {
        const visible = progress(frame, h.at, 10) * (h.until ? 1 - progress(frame, h.until, 8) : 1);
        return (
          <div
            key={`${h.x}-${h.y}`}
            style={{
              position: "absolute",
              left: (h.x - view.x) * scale - 6,
              top: (h.y - view.y) * scale - 6,
              width: h.w * scale + 12,
              height: h.h * scale + 12,
              border: `3px solid ${COLORS.accent}`,
              borderRadius: 10,
              opacity: visible,
              boxShadow: "0 0 24px rgba(56,189,248,0.45)",
            }}
          />
        );
      })}
    </div>
  );
};
