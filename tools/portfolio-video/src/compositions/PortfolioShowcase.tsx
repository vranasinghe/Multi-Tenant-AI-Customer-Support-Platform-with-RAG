import type { FC } from "react";
import { AbsoluteFill, Sequence } from "remotion";

import { AudioTracks, audioFiles } from "../components/AudioTracks";
import { Captions } from "../components/Captions";
import { ProgressIndicator } from "../components/ProgressIndicator";
import { DISSOLVE } from "../components/SceneShell";
import captions from "../data/generated/showcase-captions.json";
import { SHOWCASE_CLICKS, SHOWCASE_FRAMES, showcaseTimeline, type SceneId } from "../data/showcase";
import { A1Hook } from "../scenes/showcase/A1Hook";
import { A2Product } from "../scenes/showcase/A2Product";
import { A3Works } from "../scenes/showcase/A3Works";
import { A4Underneath } from "../scenes/showcase/A4Underneath";
import { A5Evidence } from "../scenes/showcase/A5Evidence";
import { A6Close } from "../scenes/showcase/A6Close";
import "../styles/fonts";
import { COLORS, SANS } from "../styles/theme";

export const SHOWCASE_SCENE_COMPONENTS: Record<SceneId, FC> = {
  A1: A1Hook,
  A2: A2Product,
  A3: A3Works,
  A4: A4Underneath,
  A5: A5Evidence,
  A6: A6Close,
};

export type VideoProps = { variant: "preview" | "final"; captions: boolean };

/** A preview always says so, and says when there is no narration. */
export const PreviewMark = ({ variant }: { variant: VideoProps["variant"] }) => {
  const silent = !audioFiles("showcase").voice;
  if (variant === "final" && !silent) return null;
  return (
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
        textAlign: "center",
        lineHeight: 1.4,
      }}
    >
      {silent ? "SILENT PREVIEW" : "PREVIEW"}
      <br />
      NOT FOR PUBLICATION
    </div>
  );
};

export const PortfolioShowcase = ({ variant, captions: showCaptions }: VideoProps) => (
  <AbsoluteFill style={{ backgroundColor: COLORS.background }}>
    {showcaseTimeline.map((scene, index) => {
      const Scene = SHOWCASE_SCENE_COMPONENTS[scene.id];
      const last = index === showcaseTimeline.length - 1;
      return (
        <Sequence
          key={scene.id}
          from={scene.from}
          durationInFrames={scene.frames + (last ? 0 : DISSOLVE)}
          name={`${scene.id} ${scene.name}`}
        >
          <Scene />
        </Sequence>
      );
    })}
    {showCaptions ? <Captions cues={captions} /> : null}
    <ProgressIndicator />
    <PreviewMark variant={variant} />
    <AudioTracks video="showcase" clicks={SHOWCASE_CLICKS} durationInFrames={SHOWCASE_FRAMES} />
  </AbsoluteFill>
);
