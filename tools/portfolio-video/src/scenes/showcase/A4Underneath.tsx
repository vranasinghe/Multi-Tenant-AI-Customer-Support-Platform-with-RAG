import { EvidenceLabel } from "../../components/EvidenceLabel";
import { SceneShell } from "../../components/SceneShell";
import { TechnicalDiagram } from "../../components/TechnicalDiagram";
import { useRise } from "../../animations";
import { COLORS, SANS } from "../../styles/theme";

export const A4Underneath = () => {
  const stack = useRise(20);
  return (
    <SceneShell evidence={<EvidenceLabel kind="diagram" />}>
      <div
        style={{
          ...stack,
          position: "absolute",
          top: 32,
          left: 480,
          right: 48,
          textAlign: "right",
          color: COLORS.white,
          fontFamily: SANS,
          fontSize: 30,
          fontWeight: 700,
        }}
      >
        Next.js · FastAPI · PostgreSQL + pgvector · Redis + Celery
      </div>
      <div style={{ position: "absolute", top: 90, left: 30 }}>
        {/* Layers in order: clients, web and API, data, workers, providers. */}
        <TechnicalDiagram
          file="D01-architecture.svg"
          reveal={[4, 60, 140, 225, 300]}
          width={1860}
          height={862}
          viewBox={[0, 170, 1920, 890]}
        />
      </div>
    </SceneShell>
  );
};
