import { Img, staticFile } from "remotion";

import { COLORS, SANS } from "../styles/theme";

const KINDS = {
  footage: { text: "REAL APPLICATION FOOTAGE", color: COLORS.accent },
  diagram: { text: "DIAGRAM FROM SOURCE CODE", color: COLORS.accent },
  stored: { text: "STORED TEST EVIDENCE", color: COLORS.green },
  illustrative: { text: "ILLUSTRATIVE", color: COLORS.amber },
  planned: { text: "PLANNED · NOT BUILT", color: COLORS.amber },
} as const;

export type EvidenceKind = keyof typeof KINDS;

/** Says what the viewer is looking at: footage, diagram, stored evidence or plan. */
export const EvidenceLabel = ({ kind, note }: { kind: EvidenceKind; note?: string }) => {
  const { text, color } = KINDS[kind];
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 10,
        height: 44,
        padding: "0 20px",
        borderRadius: 22,
        background: COLORS.background,
        border: `2px solid ${color}`,
        fontFamily: SANS,
        fontSize: 17,
        fontWeight: 700,
        letterSpacing: 1,
        color,
      }}
    >
      {text}
      {note ? (
        <span style={{ color: COLORS.muted, fontWeight: 500, letterSpacing: 0 }}>{note}</span>
      ) : null}
    </div>
  );
};

/** The package's “local validation” label, required on every measured result. */
export const LocalValidationLabel = () => (
  <Img src={staticFile("graphics/label-local.svg")} style={{ height: 44 }} />
);
