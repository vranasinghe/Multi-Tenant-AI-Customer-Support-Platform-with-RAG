import { AbsoluteFill, useCurrentFrame } from "remotion";

import { progress, useRise } from "../animations";
import { COLORS, SANS } from "../styles/theme";

/** Closing identity. No repository link: the reviewed code is not published yet (fact check X1). */
export const EndCard = () => {
  const frame = useCurrentFrame();
  const draw = progress(frame, 4, 40);
  const title = useRise(10, 16);
  const roles = useRise(34);
  const portfolio = useRise(52);
  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(circle at 50% 42%, rgba(37,99,235,0.22), ${COLORS.background} 55%)`,
        backgroundColor: COLORS.background,
        alignItems: "center",
        justifyContent: "center",
        fontFamily: SANS,
        paddingBottom: 90,
      }}
    >
      <svg width={1500} height={560} style={{ position: "absolute", top: 190, left: 210 }}>
        <rect
          x={3}
          y={3}
          width={1494}
          height={554}
          rx={28}
          fill="none"
          stroke={COLORS.blue}
          strokeWidth={4}
          pathLength={1}
          strokeDasharray="1 1"
          strokeDashoffset={1 - draw}
        />
      </svg>
      <div
        style={{
          ...title,
          color: COLORS.white,
          fontSize: 70,
          fontWeight: 700,
          textAlign: "center",
          lineHeight: 1.25,
        }}
      >
        Multi-Tenant AI Customer Support
        <br />
        Platform with RAG
      </div>
      <div style={{ ...roles, color: COLORS.muted, fontSize: 30, marginTop: 44 }}>
        Software Engineering · Full-Stack Development · AI Engineering
      </div>
      <div
        style={{ ...portfolio, color: COLORS.accent, fontSize: 40, fontWeight: 700, marginTop: 50 }}
      >
        Portfolio: venuja.online
      </div>
      <div style={{ ...portfolio, color: COLORS.muted, fontSize: 21, marginTop: 40 }}>
        AI-generated narration (Kokoro-82M) · demonstration recorded locally with fictional data
      </div>
    </AbsoluteFill>
  );
};
