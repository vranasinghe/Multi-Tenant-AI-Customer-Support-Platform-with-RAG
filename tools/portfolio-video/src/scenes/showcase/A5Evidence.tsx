import { AbsoluteFill, Sequence, useCurrentFrame } from "remotion";

import { progress } from "../../animations";
import { ComparisonCard } from "../../components/ComparisonCard";
import { EvidenceLabel, LocalValidationLabel } from "../../components/EvidenceLabel";
import { LowerThird } from "../../components/LowerThird";
import { MetricCounter } from "../../components/MetricCounter";
import { SceneShell } from "../../components/SceneShell";
import { TechnicalDiagram } from "../../components/TechnicalDiagram";
import { TestResultChart } from "../../components/TestResultChart";
import { FINDINGS_CLOSED, FINDINGS_TOTAL, SUITES, TOTAL_PASSED } from "../../data/metrics";
import { COLORS } from "../../styles/theme";

const Panel = ({ children }: { children: React.ReactNode }) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ opacity: progress(frame, 0, 8), backgroundColor: COLORS.background }}>
      {children}
    </AbsoluteFill>
  );
};

export const A5Evidence = () => (
  <SceneShell>
    <Sequence durationInFrames={158} name="Findings">
      <div style={{ position: "absolute", top: 130, left: 30 }}>
        <TechnicalDiagram
          file="D10-remediation-timeline.svg"
          reveal={[8, 16, 24, 32, 40, 48, 56, 78]}
          width={1860}
          height={727}
          viewBox={[0, 330, 1920, 750]}
        />
      </div>
      <div style={{ position: "absolute", left: 48, top: 868 }}>
        <LowerThird
          text={`${FINDINGS_CLOSED} of ${FINDINGS_TOTAL} audit findings: local pass`}
          color={COLORS.green}
          at={60}
        />
      </div>
    </Sequence>

    <Sequence from={150} durationInFrames={98} name="Test growth">
      <Panel>
        <div style={{ position: "absolute", top: 100, left: 30 }}>
          <TechnicalDiagram
            file="D11-test-growth.svg"
            reveal={[0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 50, 56]}
            width={1860}
            height={843}
            viewBox={[0, 200, 1920, 870]}
            growBars
          />
        </div>
      </Panel>
    </Sequence>

    <Sequence from={240} durationInFrames={98} name="Total">
      <Panel>
        <div style={{ position: "absolute", top: 270, left: 120, width: 760 }}>
          <MetricCounter
            value={TOTAL_PASSED}
            label="tests passing locally"
            size={190}
            frames={32}
          />
        </div>
        <div style={{ position: "absolute", top: 370, left: 940 }}>
          <TestResultChart results={SUITES} at={8} width={860} />
        </div>
      </Panel>
    </Sequence>

    <Sequence from={330} name="Not yet verified">
      <Panel>
        <div style={{ position: "absolute", top: 260, left: 240 }}>
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
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: 660,
            display: "flex",
            justifyContent: "center",
          }}
        >
          <LowerThird
            text="AI quality and production readiness: not yet verified"
            color={COLORS.amber}
            at={24}
          />
        </div>
      </Panel>
    </Sequence>

    {/* Labels sit above the panels so they stay visible for the whole scene. */}
    <div style={{ position: "absolute", top: 28, left: 48 }}>
      <EvidenceLabel kind="stored" />
    </div>
    <div style={{ position: "absolute", top: 28, right: 48 }}>
      <LocalValidationLabel />
    </div>
  </SceneShell>
);
