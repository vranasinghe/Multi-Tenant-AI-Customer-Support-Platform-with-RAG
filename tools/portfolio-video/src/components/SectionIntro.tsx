import { useRise } from "../animations";
import { COLORS, SANS } from "../styles/theme";

/** Kicker and heading that open a section. */
export const SectionIntro = ({
  kicker,
  title,
  at = 0,
}: {
  kicker: string;
  title: string;
  at?: number;
}) => {
  const first = useRise(at);
  const second = useRise(at + 6);
  return (
    <div style={{ fontFamily: SANS }}>
      <div
        style={{ ...first, color: COLORS.accent, fontSize: 22, fontWeight: 600, letterSpacing: 3 }}
      >
        {kicker.toUpperCase()}
      </div>
      <div style={{ ...second, color: COLORS.white, fontSize: 44, fontWeight: 700, marginTop: 8 }}>
        {title}
      </div>
    </div>
  );
};
