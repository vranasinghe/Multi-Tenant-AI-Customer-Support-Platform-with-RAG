import { useRise } from "../animations";
import { COLORS, SANS } from "../styles/theme";

export type Column = { title: string; color: string; items: string[] };

const Card = ({ column, at, width }: { column: Column; at: number; width: number }) => {
  const style = useRise(at, 14, 24);
  return (
    <div
      style={{
        ...style,
        width,
        background: COLORS.surface,
        border: `2px solid ${column.color}`,
        borderRadius: 20,
        padding: "30px 38px",
        fontFamily: SANS,
      }}
    >
      <div style={{ color: column.color, fontSize: 32, fontWeight: 700, marginBottom: 18 }}>
        {column.title}
      </div>
      {column.items.map((item) => (
        <div key={item} style={{ color: COLORS.white, fontSize: 27, lineHeight: 1.75 }}>
          {item}
        </div>
      ))}
    </div>
  );
};

/** Two states side by side: before and after, or established and not yet established. */
export const ComparisonCard = ({
  left,
  right,
  at = 0,
  delay = 18,
  width = 700,
}: {
  left: Column;
  right: Column;
  at?: number;
  delay?: number;
  width?: number;
}) => (
  <div style={{ display: "flex", gap: 40, alignItems: "stretch" }}>
    <Card column={left} at={at} width={width} />
    <Card column={right} at={at + delay} width={width} />
  </div>
);
