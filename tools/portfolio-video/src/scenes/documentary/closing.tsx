import type { FC } from "react";
import { Sequence } from "remotion";

import { useRise } from "../../animations";
import { BigScreen } from "../../components/BigScreen";
import type { SceneProps } from "../../compositions/TimedVideo";
import { COLORS, SANS } from "../../styles/theme";
import { A6Close } from "../showcase/A6Close";
import { Card, Centered, Diagram, Labels, Note, Panel, Shell, steps } from "./shared";

// Neutral wording: the process is documented in the repository; no individual achievement is
// attributed until the author confirms it (fact check, items C1–C10).
const PROCESS = [
  "Written requirements",
  "Explicit acceptance criteria",
  "Baseline measurements",
  "Focused remediation",
  "Documented validation",
];

const EVIDENCE = [
  "Improvement plan and progress tracker",
  "One report per fix and checkpoint",
  "Stored test logs, including failures",
];

const Row = ({ text, at, color }: { text: string; at: number; color: string }) => {
  const style = useRise(at);
  return (
    <div
      style={{
        ...style,
        padding: "18px 26px",
        borderRadius: 12,
        background: COLORS.surface,
        border: `2px solid ${color}`,
        color: COLORS.white,
        fontSize: 29,
      }}
    >
      {text}
    </div>
  );
};

export const Contribution: FC<SceneProps> = () => (
  <Shell>
    <div style={{ position: "absolute", top: 130, left: 210, width: 1500, fontFamily: SANS }}>
      <Note at={10} color={COLORS.white} size={46}>
        Undergraduate portfolio project, developed with AI coding assistants
      </Note>
      <Note at={30} size={30} style={{ marginTop: 14 }}>
        including Codex and Claude Code
      </Note>
      <div style={{ display: "flex", gap: 60, marginTop: 60 }}>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 18 }}>
          {PROCESS.map((text, i) => (
            <Row key={text} text={text} at={160 + i * 70} color={COLORS.blue} />
          ))}
        </div>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 18 }}>
          {EVIDENCE.map((text, i) => (
            <Row key={text} text={text} at={460 + i * 50} color={COLORS.green} />
          ))}
          <Note at={620} size={30} style={{ marginTop: 18 }}>
            Failures kept on record · decisions needing approval held
          </Note>
        </div>
      </div>
    </div>
  </Shell>
);

const OPEN_ITEMS = [
  ["Real AI evaluation", "Answer correctness is untested."],
  ["Semantic retrieval quality", "Offline Recall@5 85% against a 90% target."],
  ["Hosted CI", "Configured, never run."],
  ["Migration policy", "Approval still pending."],
  ["Production deployment", "Not completed."],
  ["Parser sandboxing", "Contained, not sandboxed."],
  ["Backup at scale", "Off-site and production-size recovery untested."],
  ["Monitoring and alerting", "Not in place."],
] as const;

export const WhereItStands: FC<SceneProps> = () => (
  <Shell>
    <Sequence durationInFrames={330}>
      <Diagram file="D14-roadmap.svg" reveal={steps(3, 20, 70)} viewBox={[0, 190, 1920, 890]} />
      <Labels kind="planned" />
    </Sequence>
    <Sequence from={320}>
      <Panel>
        <Note
          at={4}
          color={COLORS.white}
          size={46}
          style={{ position: "absolute", top: 120, width: 1920 }}
        >
          Still open
        </Note>
        <div
          style={{
            position: "absolute",
            top: 190,
            left: 140,
            display: "grid",
            gridTemplateColumns: "800px 800px",
            gap: 24,
          }}
        >
          {OPEN_ITEMS.map(([title, line], i) => (
            <Card
              key={title}
              at={30 + i * 40}
              width={800}
              color={COLORS.amber}
              title={title}
              lines={[line]}
            />
          ))}
        </div>
        <Note at={390} size={32} style={{ position: "absolute", top: 862, width: 1920 }}>
          Unfinished requirements, not implemented features.
        </Note>
      </Panel>
      <Labels kind="stored" />
    </Sequence>
  </Shell>
);

const CHIPS = ["7 / 7 audit findings, locally", "1,505 tests, locally", "Self-audit 85.75 / 100"];

export const Close: FC<SceneProps> = ({ segment }) => (
  <Shell>
    <Sequence durationInFrames={90}>
      <BigScreen
        clip="R15-dashboard-populated"
        caption="Organization dashboard"
        segments={[{ from: 2, frames: 80, rate: 0.4 }]}
        crop={{ x: 0, y: 0, w: 1340 }}
        to={{ x: 0, y: 0, w: 1210 }}
      />
      <Labels kind="footage" />
    </Sequence>
    <Sequence from={80} durationInFrames={90}>
      <BigScreen
        clip="R09-customer-widget"
        caption="Widget on a fictional store"
        segments={[{ from: 21.5, frames: 80, rate: 1 }]}
        crop={{ x: 840, y: 310, w: 1060 }}
      />
      <Labels kind="footage" demo />
    </Sequence>
    <Sequence from={160} durationInFrames={90}>
      <BigScreen
        clip="R12-inbox"
        caption="Conversation inbox"
        segments={[{ from: 8, frames: 80, rate: 1 }]}
        crop={{ x: 380, y: 0, w: 1360 }}
      />
      <Labels kind="footage" demo />
    </Sequence>
    <Sequence from={240} durationInFrames={90}>
      <Panel>
        <Diagram
          file="D01-architecture.svg"
          reveal={steps(5, 0, 6)}
          viewBox={[0, 170, 1920, 890]}
        />
      </Panel>
      <Labels kind="diagram" />
    </Sequence>
    <Sequence from={320} durationInFrames={90}>
      <Panel>
        <Centered>
          {CHIPS.map((chip, i) => (
            <Card
              key={chip}
              at={6 + i * 12}
              width={900}
              color={COLORS.green}
              size={40}
              title={chip}
            />
          ))}
          <Note at={46} size={26}>
            Local validation · self-scored, not independent certification
          </Note>
        </Centered>
      </Panel>
      <Labels kind="stored" local />
    </Sequence>
    <Sequence from={400}>
      <A6Close frames={segment.frames - 400} />
    </Sequence>
  </Shell>
);
