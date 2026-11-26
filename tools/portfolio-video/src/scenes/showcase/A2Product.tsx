import { Sequence, useCurrentFrame } from "remotion";

import { progress } from "../../animations";
import { CinematicTitle } from "../../components/CinematicTitle";
import { EvidenceLabel } from "../../components/EvidenceLabel";
import { SceneShell } from "../../components/SceneShell";
import { COLORS, SANS } from "../../styles/theme";
import { FootageShot } from "./FootageShot";

const W = 1320;
const H = 742;

/** Title over the wizard, lifted before the chatbot is created. */
const TitleScrim = () => {
  const frame = useCurrentFrame();
  const scrim = progress(frame, 24, 12) * (1 - progress(frame, 150, 14));
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        background: `rgba(8,12,20,${0.86 * scrim})`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        opacity: scrim > 0 ? 1 : 0,
      }}
    >
      <div style={{ opacity: scrim, width: 1180 }}>
        <CinematicTitle
          text="Multi-Tenant AI Customer Support Platform with RAG"
          at={30}
          size={58}
        />
      </div>
    </div>
  );
};

const SpeedTag = () => (
  <div
    style={{
      position: "absolute",
      right: 16,
      bottom: 16,
      padding: "6px 14px",
      borderRadius: 8,
      background: COLORS.background,
      color: COLORS.white,
      fontFamily: SANS,
      fontSize: 22,
      fontWeight: 700,
    }}
  >
    ×2.5
  </div>
);

export const A2Product = () => (
  <SceneShell evidence={<EvidenceLabel kind="footage" note="Fictional business and data" />}>
    <Sequence durationInFrames={218} name="Wizard">
      <FootageShot
        caption="Create a chatbot (sped up)"
        clip="R03-create-chatbot"
        // The wizard's model step is left out: it names real models, and none was run.
        segments={[
          { from: 4, frames: 119, rate: 2.5 },
          // The model step starts near 19 s: stop at 18.2 s.
          { from: 14, frames: 50, rate: 2.5 },
          { from: 26.4, frames: 41, rate: 1.4 },
        ]}
        width={W}
        height={H}
        crop={{ x: 0, y: 0, w: 1920 }}
        overlay={
          <>
            <SpeedTag />
            <TitleScrim />
          </>
        }
      />
    </Sequence>
    <Sequence from={210} name="Processing">
      <FootageShot
        fadeIn
        caption="Knowledge base: Queued → Processing → Ready"
        clip="R04-upload-and-process"
        segments={[{ from: 3.3, frames: 180, rate: 1 }]}
        width={W}
        height={H}
        crop={{ x: 0, y: 0, w: 1920 }}
        zoomTo={{ x: 420, y: 518, w: 1000 }}
        zoomAt={24}
        zoomFrames={30}
      />
    </Sequence>
  </SceneShell>
);
