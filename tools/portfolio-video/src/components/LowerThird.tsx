import { useRise } from "../animations";
import { COLORS, SANS } from "../styles/theme";

/** Short on-screen statement with a coloured rule. */
export const LowerThird = ({
  text,
  detail,
  at = 0,
  color = COLORS.blue,
}: {
  text: string;
  detail?: string;
  at?: number;
  color?: string;
}) => {
  const style = useRise(at);
  return (
    <div
      style={{
        ...style,
        display: "inline-flex",
        alignItems: "center",
        gap: 18,
        padding: "12px 28px 12px 0",
        borderRadius: 12,
        background: COLORS.surface,
        fontFamily: SANS,
        overflow: "hidden",
      }}
    >
      <div style={{ width: 6, alignSelf: "stretch", background: color }} />
      <div>
        <div style={{ color: COLORS.white, fontSize: 32, fontWeight: 700 }}>{text}</div>
        {detail ? (
          <div style={{ color: COLORS.muted, fontSize: 20, marginTop: 2 }}>{detail}</div>
        ) : null}
      </div>
    </div>
  );
};
