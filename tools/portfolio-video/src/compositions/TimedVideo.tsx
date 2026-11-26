import type { FC } from "react";
import { AbsoluteFill, Freeze, interpolate, Sequence, useCurrentFrame } from "remotion";

import { Captions, type Cue } from "../components/Captions";
import { ProgressIndicator } from "../components/ProgressIndicator";
import { DISSOLVE } from "../components/SceneShell";
import "../styles/fonts";
import { COLORS, SANS } from "../styles/theme";

export type Segment = {
  id: string;
  title: string;
  chapter: number;
  chapterTitle: string;
  from: number;
  frames: number;
  /** Length the scene's visuals were designed on, and [video frame, design frame] pairs. */
  design: number;
  knots: number[][];
};

export type Script = { frames: number; segments: Segment[]; captions: Cue[] };

export type VideoProps = { variant: "preview" | "final"; captions: boolean };

export type SceneProps = { segment: Segment };

const PreviewMark = ({ variant }: { variant: VideoProps["variant"] }) =>
  variant === "final" ? null : (
    <div
      style={{
        position: "absolute",
        right: 24,
        bottom: 18,
        padding: "5px 14px",
        borderRadius: 8,
        border: `2px solid ${COLORS.amber}`,
        background: COLORS.background,
        color: COLORS.amber,
        fontFamily: SANS,
        fontSize: 16,
        fontWeight: 700,
      }}
    >
      PREVIEW · NOT FOR PUBLICATION
    </div>
  );

/**
 * Plays a scene on its design timeline while the video runs on the narration's: each shot is moved
 * to meet the sentence about it. Past the end it runs on, for the cross-dissolve.
 */
const Warped = ({ segment, Scene }: { segment: Segment; Scene: FC<SceneProps> }) => {
  const frame = useCurrentFrame();
  const design =
    frame >= segment.frames
      ? segment.design + (frame - segment.frames)
      : interpolate(
          frame,
          segment.knots.map((k) => k[0]!),
          segment.knots.map((k) => k[1]!),
        );
  return (
    <Freeze frame={Math.floor(design)}>
      <Scene segment={{ ...segment, frames: segment.design }} />
    </Freeze>
  );
};

/**
 * Lays scenes out from a generated script and adds captions and the preview mark. The picture is
 * rendered silent; scripts/mix.py adds narration, music and effects.
 */
export const TimedVideo = ({
  script,
  scenes,
  variant,
  captions,
  overlay: Overlay,
}: VideoProps & {
  script: Script;
  scenes: Record<string, FC<SceneProps>>;
  overlay?: FC;
}) => (
  <AbsoluteFill style={{ backgroundColor: COLORS.background }}>
    {script.segments.map((segment, index) => {
      const Scene = scenes[segment.id];
      if (!Scene) throw new Error(`no scene for ${segment.id}`);
      const last = index === script.segments.length - 1;
      return (
        <Sequence
          key={segment.id}
          from={segment.from}
          durationInFrames={segment.frames + (last ? 0 : DISSOLVE)}
          name={`${segment.id} ${segment.title}`}
        >
          <Warped segment={segment} Scene={Scene} />
        </Sequence>
      );
    })}
    {Overlay ? <Overlay /> : null}
    {captions ? <Captions cues={script.captions} /> : null}
    <ProgressIndicator />
    <PreviewMark variant={variant} />
  </AbsoluteFill>
);
