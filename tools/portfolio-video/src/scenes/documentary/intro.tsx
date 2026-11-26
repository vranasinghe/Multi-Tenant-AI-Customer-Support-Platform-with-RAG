import type { FC } from "react";
import { AbsoluteFill, Sequence, useCurrentFrame } from "remotion";

import { progress, useRise } from "../../animations";
import { BigScreen } from "../../components/BigScreen";
import { CinematicTitle } from "../../components/CinematicTitle";
import { SceneShell } from "../../components/SceneShell";
import type { SceneProps } from "../../compositions/TimedVideo";
import { COLORS, SANS } from "../../styles/theme";
import { Labels, Shell } from "./shared";

const TitleReveal = () => {
  const why = useRise(36, 14, 20);
  const rule = progress(useCurrentFrame(), 24, 30);
  return (
    <AbsoluteFill
      style={{
        alignItems: "center",
        justifyContent: "center",
        paddingBottom: 100,
        fontFamily: SANS,
      }}
    >
      <div style={{ width: 1500 }}>
        <CinematicTitle text="Beyond a Chatbot" at={-8} size={118} />
      </div>
      <div
        style={{
          width: 760 * rule,
          height: 6,
          borderRadius: 3,
          background: COLORS.blue,
          margin: "40px 0",
        }}
      />
      <div style={{ ...why, color: COLORS.white, fontSize: 40, fontWeight: 500 }}>
        Engineering a Multi-Tenant AI Customer Support Platform
      </div>
    </AbsoluteFill>
  );
};

export const Opening: FC<SceneProps> = () => (
  <SceneShell fadeIn={false}>
    <Sequence durationInFrames={190}>
      <TitleReveal />
    </Sequence>
    <Sequence from={180} durationInFrames={120}>
      <BigScreen
        clip="R15-dashboard-populated"
        caption="Organization dashboard"
        label="Dashboard"
        segments={[{ from: 2, frames: 110, rate: 0.4 }]}
        crop={{ x: 0, y: 0, w: 1340 }}
        to={{ x: 0, y: 0, w: 1210 }}
      />
    </Sequence>
    <Sequence from={290} durationInFrames={125}>
      <BigScreen
        clip="R05-retrieval-test"
        caption="Knowledge base"
        label="Knowledge base"
        segments={[{ from: 12, frames: 115, rate: 0.6 }]}
        crop={{ x: 320, y: 180, w: 1600 }}
        to={{ x: 420, y: 330, w: 1300 }}
      />
    </Sequence>
    <Sequence from={405} durationInFrames={125}>
      <BigScreen
        clip="R09-customer-widget"
        caption="Widget on a fictional store"
        label="Customer widget"
        segments={[{ from: 6.4, frames: 115, rate: 1 }]}
        crop={{ x: 0, y: 0, w: 1920 }}
        to={{ x: 590, y: 310, w: 1330 }}
        moveFrames={60}
      />
    </Sequence>
    <Sequence from={520}>
      <BigScreen
        clip="R12-inbox"
        caption="Conversation inbox"
        label="Team inbox"
        segments={[{ from: 10.9, frames: 110, rate: 0.5 }]}
        crop={{ x: 320, y: 0, w: 1600 }}
        to={{ x: 420, y: 0, w: 1300 }}
      />
    </Sequence>
    <Sequence from={180} durationInFrames={110}>
      <Labels kind="footage" />
    </Sequence>
    <Sequence from={290}>
      <Labels kind="footage" demo />
    </Sequence>
  </SceneShell>
);

const QUESTIONS = [
  "When can I return this?",
  "How long does shipping take?",
  "What does the warranty cover?",
  "Can I return this after two weeks?",
  "Where is my order?",
];
const SOURCES = [
  "Returns policy",
  "Shipping page",
  "Warranty document",
  "Care guide",
  "Help pages",
];

const Chip = ({
  x,
  y,
  at,
  text,
  color,
}: {
  x: number;
  y: number;
  at: number;
  text: string;
  color: string;
}) => {
  const style = useRise(at, 14, 24);
  return (
    <div
      style={{
        ...style,
        position: "absolute",
        left: x,
        top: y,
        padding: "16px 26px",
        borderRadius: 14,
        background: COLORS.surface,
        border: `2px solid ${color}`,
        color: COLORS.white,
        fontSize: 28,
        whiteSpace: "nowrap",
      }}
    >
      {text}
    </div>
  );
};

const Business = ({
  x,
  name,
  color,
  at,
}: {
  x: number;
  name: string;
  color: string;
  at: number;
}) => {
  const style = useRise(at);
  return (
    <div
      style={{
        ...style,
        position: "absolute",
        left: x,
        top: 240,
        width: 640,
        height: 440,
        borderRadius: 20,
        border: `3px solid ${color}`,
        background: COLORS.surface,
        textAlign: "center",
        color: COLORS.white,
      }}
    >
      <div style={{ fontSize: 40, fontWeight: 700, marginTop: 40 }}>{name}</div>
      {["Its own documents", "Its own conversations", "Its own customers"].map((item) => (
        <div key={item} style={{ fontSize: 30, color: COLORS.muted, marginTop: 40 }}>
          {item}
        </div>
      ))}
    </div>
  );
};

const Line = ({ top, color, children }: { top: number; color: string; children: string }) => (
  <div style={{ position: "absolute", top, width: 1920, textAlign: "center", color, fontSize: 34 }}>
    {children}
  </div>
);

/** An illustration, labelled as one: no figures, no real customers. */
export const Problem: FC<SceneProps> = () => (
  <Shell kind="illustrative" note="Fictional examples">
    <AbsoluteFill style={{ fontFamily: SANS }}>
      <Sequence durationInFrames={338}>
        {QUESTIONS.map((q, i) => (
          <Chip
            key={q}
            x={160 + (i % 2) * 90}
            y={140 + i * 122}
            at={6 + i * 22}
            text={q}
            color={COLORS.blue}
          />
        ))}
        {SOURCES.map((s, i) => (
          <Chip
            key={s}
            x={1240 + ((i * 3) % 4) * 60}
            y={160 + i * 120}
            at={140 + i * 14}
            text={s}
            color={COLORS.muted}
          />
        ))}
        <Line top={790} color={COLORS.muted}>
          Same questions, repeated · answers spread across documents and pages
        </Line>
      </Sequence>
      <Sequence from={330} durationInFrames={248}>
        <AbsoluteFill style={{ background: COLORS.background }}>
          <Chip
            x={420}
            y={220}
            at={8}
            text="“Can I return this after two weeks?”"
            color={COLORS.blue}
          />
          <Chip
            x={560}
            y={420}
            at={44}
            text="Find the passage in the business’s own material"
            color={COLORS.accent}
          />
          <Chip
            x={700}
            y={620}
            at={80}
            text="Answer, and show which source was used"
            color={COLORS.green}
          />
        </AbsoluteFill>
      </Sequence>
      <Sequence from={570}>
        <AbsoluteFill style={{ background: COLORS.background }}>
          <Business x={200} name="Business A" color={COLORS.blue} at={6} />
          <Business x={1080} name="Business B" color={COLORS.accent} at={20} />
          <div
            style={{
              position: "absolute",
              left: 957,
              top: 220,
              width: 6,
              height: 480,
              background: COLORS.amber,
            }}
          />
          <Line top={770} color={COLORS.white}>
            One shared platform. Every answer from the right business, and only that one.
          </Line>
        </AbsoluteFill>
      </Sequence>
    </AbsoluteFill>
  </Shell>
);
