import type { CSSProperties, ReactNode } from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";

import { progress, useRise } from "../../animations";
import { DemoWarning } from "../../components/DemoWarning";
import {
  EvidenceLabel,
  LocalValidationLabel,
  type EvidenceKind,
} from "../../components/EvidenceLabel";
import { SceneShell } from "../../components/SceneShell";
import { TechnicalDiagram } from "../../components/TechnicalDiagram";
import { COLORS, SANS } from "../../styles/theme";

export const Footage = () => <EvidenceLabel kind="footage" note="Fictional business and data" />;

/** Scene background with the "what am I looking at" and demo / local-validation labels. */
export const Shell = ({
  kind,
  note,
  demo,
  local,
  children,
}: {
  kind?: EvidenceKind;
  note?: string;
  demo?: boolean;
  local?: boolean;
  children: ReactNode;
}) => (
  <SceneShell
    evidence={kind ? <EvidenceLabel kind={kind} note={note} /> : undefined}
    warning={demo ? <DemoWarning /> : local ? <LocalValidationLabel /> : undefined}
  >
    {children}
  </SceneShell>
);

/** Labels that must stay above layers which paint their own background. */
export const Labels = ({
  kind,
  demo,
  local,
}: {
  kind?: EvidenceKind;
  demo?: boolean;
  local?: boolean;
}) => (
  <>
    {kind ? (
      <div style={{ position: "absolute", top: 28, left: 48 }}>
        {kind === "footage" ? <Footage /> : <EvidenceLabel kind={kind} />}
      </div>
    ) : null}
    <div style={{ position: "absolute", top: 28, right: 48 }}>
      {demo ? <DemoWarning /> : local ? <LocalValidationLabel /> : null}
    </div>
  </>
);

/** A layer that covers whatever was on screen before it, with a short fade. */
export const Panel = ({ children }: { children: ReactNode }) => (
  <AbsoluteFill
    style={{ opacity: progress(useCurrentFrame(), 0, 8), backgroundColor: COLORS.background }}
  >
    {children}
  </AbsoluteFill>
);

/** Reveal frames for `count` diagram layers, evenly spaced. */
export const steps = (count: number, at: number, gap: number) =>
  Array.from({ length: count }, (_, i) => at + i * gap);

type DiagramProps = Omit<Parameters<typeof TechnicalDiagram>[0], "width" | "height"> & {
  width?: number;
  height?: number;
  top?: number;
  left?: number;
};

export const Diagram = ({
  width = 1824,
  height = 805,
  top = 100,
  left,
  ...props
}: DiagramProps) => (
  <div style={{ position: "absolute", top, left: left ?? (1920 - width) / 2 }}>
    <TechnicalDiagram width={width} height={height} {...props} />
  </div>
);

export const Card = ({
  at = 0,
  title,
  color = COLORS.blue,
  lines = [],
  width = 800,
  size = 34,
  lineSize = size * 0.72,
}: {
  at?: number;
  title: string;
  color?: string;
  lines?: string[];
  width?: number;
  size?: number;
  lineSize?: number;
}) => {
  const style = useRise(at);
  return (
    <div
      style={{
        ...style,
        width,
        boxSizing: "border-box",
        padding: "26px 34px",
        borderRadius: 16,
        background: COLORS.surface,
        border: `2px solid ${color}`,
        fontFamily: SANS,
      }}
    >
      <div style={{ color: COLORS.white, fontSize: size, fontWeight: 700 }}>{title}</div>
      {lines.map((line) => (
        <div
          key={line}
          style={{ color: COLORS.muted, fontSize: lineSize, marginTop: 12, lineHeight: 1.4 }}
        >
          {line}
        </div>
      ))}
    </div>
  );
};

export const Centered = ({ children, gap = 36 }: { children: ReactNode; gap?: number }) => (
  <AbsoluteFill
    style={{
      alignItems: "center",
      justifyContent: "center",
      flexDirection: "column",
      gap,
      paddingBottom: 100,
      fontFamily: SANS,
    }}
  >
    {children}
  </AbsoluteFill>
);

export const Note = ({
  at = 0,
  color = COLORS.muted,
  size = 28,
  style,
  children,
}: {
  at?: number;
  color?: string;
  size?: number;
  style?: CSSProperties;
  children: ReactNode;
}) => {
  const rise = useRise(at);
  return (
    <div
      style={{ ...rise, color, fontSize: size, textAlign: "center", fontFamily: SANS, ...style }}
    >
      {children}
    </div>
  );
};
