import type { FC } from "react";
import { AbsoluteFill, Sequence, useCurrentFrame } from "remotion";

import { progress, useRise } from "../../animations";
import { BigScreen } from "../../components/BigScreen";
import { CinematicTitle } from "../../components/CinematicTitle";
import { ComparisonCard } from "../../components/ComparisonCard";
import { DemoWarning } from "../../components/DemoWarning";
import { BackendGrowth, FindingsAndScore, SuiteTally } from "../../components/Evidence";
import { EvidenceLabel, LocalValidationLabel } from "../../components/EvidenceLabel";
import { LayeredArchitecture } from "../../components/LayeredArchitecture";
import { SceneShell } from "../../components/SceneShell";
import type { SceneProps } from "../../compositions/TimedVideo";
import { COLORS, SANS } from "../../styles/theme";
import { A6Close } from "../showcase/A6Close";

const Footage = () => <EvidenceLabel kind="footage" note="Fictional business and data" />;

/** What it is and why it matters, inside the first five seconds. */
const Title: FC<SceneProps> = () => {
  const why = useRise(36, 14, 20);
  const frame = useCurrentFrame();
  const rule = progress(frame, 24, 30);
  return (
    <SceneShell fadeIn={false}>
      <AbsoluteFill
        style={{
          alignItems: "center",
          justifyContent: "center",
          paddingBottom: 100,
          fontFamily: SANS,
        }}
      >
        <div style={{ width: 1500 }}>
          <CinematicTitle
            text="Multi-Tenant AI Customer Support Platform with RAG"
            at={-8}
            size={84}
          />
        </div>
        <div
          style={{
            width: 760 * rule,
            height: 6,
            borderRadius: 3,
            background: COLORS.blue,
            margin: "44px 0",
          }}
        />
        <div style={{ ...why, color: COLORS.white, fontSize: 40, fontWeight: 500 }}>
          Support answers from each business’s own documents —{" "}
          <span style={{ color: COLORS.accent, fontWeight: 700 }}>and only theirs.</span>
        </div>
      </AbsoluteFill>
    </SceneShell>
  );
};

/** Four screens, one at a time, large. */
const Montage: FC<SceneProps> = () => (
  <SceneShell evidence={<Footage />} warning={<DemoWarning />}>
    <Sequence durationInFrames={100}>
      <BigScreen
        clip="R15-dashboard-populated"
        caption="Organization dashboard"
        label="Dashboard"
        segments={[{ from: 2, frames: 90, rate: 0.4 }]}
        crop={{ x: 0, y: 0, w: 1340 }}
        to={{ x: 0, y: 0, w: 1210 }}
      />
    </Sequence>
    <Sequence from={90} durationInFrames={100}>
      <BigScreen
        clip="R03-create-chatbot"
        caption="Guided chatbot setup (model step not shown)"
        label="Create a chatbot"
        segments={[{ from: 4, frames: 90, rate: 2 }]}
        crop={{ x: 0, y: 0, w: 1920 }}
        to={{ x: 240, y: 60, w: 1560 }}
      />
    </Sequence>
    <Sequence from={180} durationInFrames={100}>
      <BigScreen
        clip="R05-retrieval-test"
        caption="Knowledge base"
        label="Knowledge base"
        segments={[{ from: 0.9, frames: 90, rate: 0.6 }]}
        crop={{ x: 320, y: 180, w: 1600 }}
        to={{ x: 420, y: 330, w: 1300 }}
      />
    </Sequence>
    <Sequence from={270} durationInFrames={85}>
      <BigScreen
        clip="R09-customer-widget"
        caption="Widget on a fictional store"
        label="Customer widget"
        // The question being typed: the reply is shown once, later.
        segments={[{ from: 6.4, frames: 75, rate: 1 }]}
        crop={{ x: 0, y: 0, w: 1920 }}
        to={{ x: 590, y: 310, w: 1330 }}
        moveFrames={50}
      />
    </Sequence>
    <Sequence from={345}>
      <BigScreen
        clip="R12-inbox"
        caption="Conversation inbox"
        label="Team inbox"
        segments={[{ from: 10.9, frames: 75, rate: 0.7 }]}
        crop={{ x: 320, y: 0, w: 1600 }}
        to={{ x: 420, y: 0, w: 1300 }}
      />
    </Sequence>
  </SceneShell>
);

const StatusCard = () => {
  const style = useRise(66);
  return (
    <div
      style={{
        ...style,
        position: "absolute",
        right: 280,
        top: 560,
        padding: "20px 30px",
        borderRadius: 14,
        background: COLORS.surface,
        border: `2px solid ${COLORS.green}`,
        fontFamily: SANS,
      }}
    >
      <div style={{ color: COLORS.muted, fontSize: 20, marginBottom: 8 }}>
        Recorded status codes · second owner
      </div>
      <div style={{ color: COLORS.white, fontSize: 30, fontWeight: 700 }}>
        First business’s data: <span style={{ color: COLORS.amber }}>404</span>
      </div>
      <div style={{ color: COLORS.white, fontSize: 30, fontWeight: 700 }}>
        Own data: <span style={{ color: COLORS.green }}>200</span>
      </div>
    </div>
  );
};

/** Six capabilities, each shown once. Demo label throughout. */
const Capabilities: FC<SceneProps> = () => (
  <SceneShell evidence={<Footage />} warning={<DemoWarning />}>
    <Sequence durationInFrames={160}>
      <BigScreen
        clip="R04-upload-and-process"
        caption="Queued → Processing → Ready"
        label="Background document processing"
        segments={[{ from: 3.3, frames: 150, rate: 1.2 }]}
        crop={{ x: 320, y: 220, w: 1480 }}
        to={{ x: 420, y: 440, w: 1100 }}
        moveFrames={50}
      />
    </Sequence>
    <Sequence from={150} durationInFrames={160}>
      {/* The crop ends above the token and cost line. */}
      <BigScreen
        clip="R07-playground"
        caption="Playground: the fixed demo reply and its source"
        label="Citation to the source document"
        labelAt="top"
        width={1600}
        height={522}
        segments={[{ from: 12, frames: 150, rate: 0.8 }]}
        crop={{ x: 330, y: 140, w: 1340 }}
        to={{ x: 436, y: 224, w: 1100 }}
        moveAt={10}
        moveFrames={30}
        highlights={[{ x: 492, y: 529, w: 278, h: 33, at: 44 }]}
      />
    </Sequence>
    <Sequence from={300} durationInFrames={190}>
      <BigScreen
        clip="R14-tenant-isolation"
        caption="Signed in as a second business"
        label="Another business is refused"
        segments={[
          { from: 1, frames: 48, rate: 1 },
          { from: 6, frames: 132, rate: 0.5 },
        ]}
        crop={{ x: 0, y: 0, w: 1920 }}
        to={{ x: 0, y: 0, w: 1400 }}
        moveAt={48}
        moveFrames={30}
      />
      <StatusCard />
    </Sequence>
    <Sequence from={480} durationInFrames={145}>
      <BigScreen
        clip="R09-customer-widget"
        caption="The visitor reloads the page and reopens the widget"
        label="Conversation survives a reload"
        segments={[
          { from: 18.4, frames: 40, rate: 1 },
          { from: 20.8, frames: 95, rate: 1 },
        ]}
        crop={{ x: 0, y: 0, w: 1920 }}
        to={{ x: 840, y: 310, w: 1060 }}
        moveAt={40}
        moveFrames={36}
      />
    </Sequence>
    <Sequence from={615} durationInFrames={130}>
      {/* Only the first metric row: the row below holds fixture cost and token figures. */}
      <BigScreen
        clip="R13-analytics"
        caption="Analytics from stored events"
        label="Synthetic demo data · “grounded” means a citation was stored"
        labelAt="top"
        width={1600}
        height={400}
        segments={[{ from: 6, frames: 120, rate: 0 }]}
        crop={{ x: 420, y: 90, w: 1420 }}
      />
    </Sequence>
    <Sequence from={735}>
      <BigScreen
        clip="R10-widget-lifecycle"
        caption="Test harness page, not part of the product"
        label="Installing twice keeps one widget"
        // Ends before the harness mounts an explicit second instance.
        segments={[{ from: 2.5, frames: 135, rate: 1.35 }]}
        crop={{ x: 0, y: 0, w: 1280 }}
        to={{ x: 0, y: 40, w: 1100 }}
      />
    </Sequence>
  </SceneShell>
);

const Architecture: FC<SceneProps> = ({ segment }) => (
  <SceneShell evidence={<EvidenceLabel kind="diagram" />}>
    <LayeredArchitecture starts={[0, 90, 180, 270, 360]} total={segment.frames} />
    <div style={{ position: "absolute", top: 28, left: 48 }}>
      <EvidenceLabel kind="diagram" />
    </div>
  </SceneShell>
);

const Panel = ({ children }: { children: React.ReactNode }) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ opacity: progress(frame, 0, 8), backgroundColor: COLORS.background }}>
      {children}
    </AbsoluteFill>
  );
};

const EvidenceScene: FC<SceneProps> = () => (
  <SceneShell>
    <Sequence durationInFrames={158}>
      <BackendGrowth second={60} />
    </Sequence>
    <Sequence from={150} durationInFrames={188}>
      <Panel>
        <SuiteTally interval={26} />
      </Panel>
    </Sequence>
    <Sequence from={330} durationInFrames={128}>
      <Panel>
        <FindingsAndScore second={40} />
      </Panel>
    </Sequence>
    <Sequence from={450}>
      <Panel>
        <div style={{ position: "absolute", top: 320, left: 240 }}>
          <ComparisonCard
            delay={12}
            left={{
              title: "Validated locally",
              color: COLORS.green,
              items: ["7 of 7 audit findings", "1,505 tests passing", "Core workflows"],
            }}
            right={{
              title: "Not yet verified",
              color: COLORS.amber,
              items: ["Real AI quality", "Production readiness", "Hosted CI"],
            }}
          />
        </div>
      </Panel>
    </Sequence>
    <div style={{ position: "absolute", top: 28, left: 48 }}>
      <EvidenceLabel kind="stored" />
    </div>
    <div style={{ position: "absolute", top: 28, right: 48 }}>
      <LocalValidationLabel />
    </div>
  </SceneShell>
);

const Close: FC<SceneProps> = ({ segment }) => <A6Close frames={segment.frames} />;

export const SHOWCASE_V2: Record<string, FC<SceneProps>> = {
  A1: Title,
  A2: Montage,
  A3: Capabilities,
  A4: Architecture,
  A5: EvidenceScene,
  A6: Close,
};
