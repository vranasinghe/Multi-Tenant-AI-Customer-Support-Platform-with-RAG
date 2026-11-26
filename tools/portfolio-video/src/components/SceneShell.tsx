import type { ReactNode } from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";

import { progress } from "../animations";
import { COLORS, LAYOUT } from "../styles/theme";

export const DISSOLVE = 8;

type Props = {
  children: ReactNode;
  /** Top-left: what the viewer is seeing. */
  evidence?: ReactNode;
  /** Top-right: the demo or local-validation label. */
  warning?: ReactNode;
  fadeIn?: boolean;
};

/** Shared background, label positions and the cross-dissolve into a scene. */
export const SceneShell = ({ children, evidence, warning, fadeIn = true }: Props) => {
  const frame = useCurrentFrame();
  const opacity = fadeIn ? progress(frame, 0, DISSOLVE) : 1;
  return (
    <AbsoluteFill
      style={{
        opacity,
        backgroundColor: COLORS.background,
        backgroundImage:
          "radial-gradient(ellipse at 50% 0%, rgba(37,99,235,0.12), transparent 60%)",
      }}
    >
      {children}
      {evidence ? (
        <div style={{ position: "absolute", top: LAYOUT.labelTop, left: LAYOUT.side }}>
          {evidence}
        </div>
      ) : null}
      {warning ? (
        <div style={{ position: "absolute", top: LAYOUT.labelTop, right: LAYOUT.side }}>
          {warning}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
