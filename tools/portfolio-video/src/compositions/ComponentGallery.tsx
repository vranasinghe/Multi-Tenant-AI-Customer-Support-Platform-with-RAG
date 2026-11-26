import type { ReactNode } from "react";
import { AbsoluteFill } from "remotion";

import { AnimatedConnection } from "../components/AnimatedConnection";
import { ArchitectureNode } from "../components/ArchitectureNode";
import { LowerThird } from "../components/LowerThird";
import { SectionIntro } from "../components/SectionIntro";
import { Timeline } from "../components/Timeline";
import { EvidenceLabel } from "../components/EvidenceLabel";
import "../styles/fonts";
import { COLORS } from "../styles/theme";

const Row = ({ children }: { children: ReactNode }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 18 }}>{children}</div>
);

/** A review sheet for the components that Video A does not use, ahead of the documentary. */
export const ComponentGallery = () => (
  <AbsoluteFill style={{ backgroundColor: COLORS.background, padding: 96, gap: 56 }}>
    <SectionIntro kicker="Component gallery" title="Building blocks for the documentary" />
    <Row>
      <ArchitectureNode title="api" detail="FastAPI" at={4} />
      <AnimatedConnection length={220} at={12} />
      <ArchitectureNode title="Redis" detail="queues" at={20} />
      <AnimatedConnection length={220} at={28} dashed color={COLORS.muted} />
      <ArchitectureNode title="worker" detail="Celery" at={36} />
    </Row>
    <Timeline
      steps={["Build", "Baseline", "Audit", "Fix", "Test", "Stabilize", "Validate", "Score"]}
      at={10}
    />
    <Row>
      <LowerThird
        text="Problem → Root cause → Solution → Validation"
        detail="Used for each engineering challenge"
      />
    </Row>
    <Row>
      <EvidenceLabel kind="footage" />
      <EvidenceLabel kind="diagram" />
      <EvidenceLabel kind="stored" />
      <EvidenceLabel kind="illustrative" />
      <EvidenceLabel kind="planned" />
    </Row>
  </AbsoluteFill>
);
