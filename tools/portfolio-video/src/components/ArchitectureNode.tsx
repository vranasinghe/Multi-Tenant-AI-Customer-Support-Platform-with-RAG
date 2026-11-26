import { useRise } from "../animations";
import { COLORS, SANS } from "../styles/theme";

/** A system component, for explanations built outside the supplied diagrams. */
export const ArchitectureNode = ({
  title,
  detail,
  at = 0,
  width = 300,
  color = COLORS.blue,
}: {
  title: string;
  detail?: string;
  at?: number;
  width?: number;
  color?: string;
}) => {
  const style = useRise(at);
  return (
    <div
      style={{
        ...style,
        width,
        padding: "22px 18px",
        borderRadius: 16,
        background: COLORS.surface,
        border: `2px solid ${color}`,
        textAlign: "center",
        fontFamily: SANS,
        boxSizing: "border-box",
      }}
    >
      <div style={{ color: COLORS.white, fontSize: 28, fontWeight: 700 }}>{title}</div>
      {detail ? (
        <div style={{ color: COLORS.muted, fontSize: 19, marginTop: 8 }}>{detail}</div>
      ) : null}
    </div>
  );
};
