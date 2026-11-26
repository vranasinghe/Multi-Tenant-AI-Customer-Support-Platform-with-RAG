import type { FC } from "react";
import { Sequence } from "remotion";

import {
  ArtifactExcerpt,
  BackendGrowth,
  CodeExcerpt,
  FindingsAndScore,
  SuiteTally,
} from "../../components/Evidence";
import { Timeline } from "../../components/Timeline";
import type { SceneProps } from "../../compositions/TimedVideo";
import { COLORS } from "../../styles/theme";
import { Card, Diagram, Labels, Note, Panel, Shell, steps } from "./shared";

export const Method: FC<SceneProps> = () => (
  <Shell>
    <Sequence durationInFrames={210}>
      <div style={{ position: "absolute", top: 420, left: 160 }}>
        <Timeline
          steps={["Build", "Baseline", "Audit", "Fix", "Test", "Stabilize", "Validate", "Score"]}
          at={40}
          interval={18}
        />
      </div>
      <Note at={150} style={{ position: "absolute", top: 600, width: 1920 }}>
        A failing test first where possible · failures are kept on record
      </Note>
    </Sequence>
    <Sequence from={200}>
      <Panel>
        <Diagram
          file="D10-remediation-timeline.svg"
          reveal={steps(8, 6, 18)}
          viewBox={[0, 200, 1920, 880]}
          top={96}
          height={820}
        />
      </Panel>
    </Sequence>
    <Labels kind="stored" local />
  </Shell>
);

export const Results: FC<SceneProps> = () => (
  <Shell>
    <Sequence durationInFrames={360}>
      <BackendGrowth second={150} />
      <Note at={250} style={{ position: "absolute", top: 830, width: 1920 }}>
        All seven audit findings pass locally.
      </Note>
    </Sequence>
    <Sequence from={350} durationInFrames={170}>
      <Panel>
        <SuiteTally interval={22} />
      </Panel>
    </Sequence>
    <Sequence from={510}>
      <Panel>
        <div
          style={{
            position: "absolute",
            top: 150,
            left: 310,
            display: "flex",
            flexDirection: "column",
            gap: 30,
          }}
        >
          <ArtifactExcerpt id="backend" width={1300} at={6} />
          <ArtifactExcerpt id="web" width={1300} at={34} />
          <ArtifactExcerpt id="browser" width={1300} at={62} />
        </div>
      </Panel>
    </Sequence>
    <Labels kind="stored" local />
  </Shell>
);

export const Failures: FC<SceneProps> = () => (
  <Shell>
    <Sequence durationInFrames={300}>
      <Diagram
        file="D11-test-growth.svg"
        reveal={steps(14, 12, 14)}
        viewBox={[0, 200, 1920, 870]}
        growBars
      />
    </Sequence>
    <Sequence from={290}>
      <Panel>
        <Note
          at={4}
          color={COLORS.white}
          size={40}
          style={{ position: "absolute", top: 110, width: 1920 }}
        >
          Fixes broken on purpose: 10 of 10 breaks were caught
        </Note>
        <div
          style={{
            position: "absolute",
            top: 180,
            left: 460,
            transform: "scale(0.85)",
            transformOrigin: "top center",
          }}
        >
          <ArtifactExcerpt id="mutantsAll" width={1000} at={16} />
        </div>
      </Panel>
    </Sequence>
    <Labels kind="stored" local />
  </Shell>
);

export const Capacity: FC<SceneProps> = () => (
  <Shell>
    <Sequence durationInFrames={340}>
      <Note
        at={30}
        color={COLORS.white}
        size={46}
        style={{ position: "absolute", top: 160, width: 1920 }}
      >
        100 concurrent chat requests
      </Note>
      <div style={{ position: "absolute", top: 300, left: 120, display: "flex", gap: 40 }}>
        <Card
          at={50}
          width={390}
          color={COLORS.green}
          size={72}
          lineSize={26}
          title="67"
          lines={["succeeded"]}
        />
        <Card
          at={90}
          width={390}
          color={COLORS.amber}
          size={72}
          lineSize={26}
          title="33"
          lines={["controlled rejection"]}
        />
        <Card
          at={130}
          width={390}
          color={COLORS.green}
          size={72}
          lineSize={26}
          title="0"
          lines={["unexpected failures"]}
        />
        <Card
          at={170}
          width={390}
          size={72}
          lineSize={26}
          title="1,682 ms"
          lines={["P95, successful requests"]}
        />
      </div>
      <Note
        at={220}
        color={COLORS.amber}
        size={32}
        style={{ position: "absolute", top: 640, width: 1920 }}
      >
        Offline fixture provider on one laptop. Not real-model or server performance.
      </Note>
    </Sequence>
    <Sequence from={330} durationInFrames={210}>
      <Panel>
        <div style={{ position: "absolute", top: 240, left: 460 }}>
          <ArtifactExcerpt id="capacity" width={1000} at={6} />
        </div>
      </Panel>
    </Sequence>
    <Sequence from={530}>
      <Panel>
        <Diagram
          file="D12-performance.svg"
          reveal={steps(4, 8, 30)}
          viewBox={[0, 190, 1920, 880]}
          top={96}
          height={820}
        />
      </Panel>
    </Sequence>
    <Labels kind="stored" local />
  </Shell>
);

export const SelfAudit: FC<SceneProps> = () => (
  <Shell>
    <Sequence durationInFrames={260}>
      <FindingsAndScore second={50} />
    </Sequence>
    <Sequence from={250}>
      <Panel>
        <Note
          at={4}
          color={COLORS.amber}
          size={44}
          style={{ position: "absolute", top: 180, width: 1920 }}
        >
          Hosted CI: configured, never run
        </Note>
        <div style={{ position: "absolute", top: 320, left: 385 }}>
          <CodeExcerpt id="ci" width={1150} at={12} />
        </div>
      </Panel>
    </Sequence>
    <Labels kind="stored" local />
  </Shell>
);
