import type { FC } from "react";
import { Sequence } from "remotion";

import { ArtifactExcerpt } from "../../components/Evidence";
import { ArchitectureView, type LayerId } from "../../components/LayeredArchitecture";
import type { SceneProps } from "../../compositions/TimedVideo";
import { COLORS } from "../../styles/theme";
import { Card, Centered, Diagram, Labels, Note, Panel, Shell, steps } from "./shared";

const view = (id: LayerId): FC<SceneProps> => {
  const View: FC<SceneProps> = () => (
    <Shell>
      <ArchitectureView layer={id} />
      <Labels kind="diagram" />
    </Shell>
  );
  return View;
};

export const Experience = view(0);
export const Application = view(1);
export const Data = view(2);
export const Intelligence = view(3);

export const Whole: FC<SceneProps> = () => (
  <Shell>
    <Sequence durationInFrames={190}>
      <ArchitectureView layer={4} />
    </Sequence>
    <Sequence from={180}>
      <Panel>
        <Diagram
          file="D01-architecture.svg"
          reveal={steps(5, 0, 8)}
          viewBox={[0, 170, 1920, 890]}
        />
      </Panel>
    </Sequence>
    <Labels kind="diagram" />
  </Shell>
);

export const Vectors: FC<SceneProps> = () => (
  <Shell kind="diagram">
    <Note
      at={40}
      color={COLORS.white}
      size={40}
      style={{ position: "absolute", top: 140, width: 1920 }}
    >
      File or web page → text → chunks → embeddings
    </Note>
    <Diagram
      file="D03-rag-pipeline.svg"
      reveal={steps(14, 40, 30)}
      viewBox={[60, 180, 900, 260]}
      camera={[{ at: 250, box: [940, 180, 900, 260], frames: 90 }]}
      top={250}
      height={527}
    />
  </Shell>
);

export const Search: FC<SceneProps> = () => (
  <Shell>
    <Sequence durationInFrames={460}>
      <Diagram
        file="D03-rag-pipeline.svg"
        reveal={steps(14, 0, 14)}
        viewBox={[0, 440, 1920, 590]}
        top={220}
        height={560}
      />
    </Sequence>
    <Sequence from={450}>
      <Panel>
        <Diagram
          file="D07-citation-provenance.svg"
          reveal={steps(7, 6, 28)}
          viewBox={[0, 170, 1920, 890]}
        />
      </Panel>
    </Sequence>
    <Labels kind="diagram" />
  </Shell>
);

export const NotEstablished: FC<SceneProps> = () => (
  <Shell>
    <Sequence durationInFrames={240}>
      <Centered>
        <Card
          at={36}
          color={COLORS.green}
          width={1300}
          title="Citation provenance: established"
          lines={["The cited source was placed in the prompt the model received."]}
        />
        <Card
          at={90}
          color={COLORS.amber}
          width={1300}
          title="Provenance is not correctness"
          lines={["It does not show that the source supports the sentence. That is not verified."]}
        />
      </Centered>
    </Sequence>
    <Sequence from={230}>
      <Panel>
        <div style={{ position: "absolute", top: 180, left: 150, width: 760 }}>
          <Note at={6} color={COLORS.amber} size={190}>
            85%
          </Note>
          <Note at={6} color={COLORS.white} size={36}>
            offline Recall@5 · 68 of 80 cases
          </Note>
          <Note at={40} size={36} style={{ marginTop: 20 }}>
            target: 90% · not met
          </Note>
          <Note at={70} style={{ marginTop: 40 }}>
            Word-matching stand-in for embeddings.
            <br />
            Real model accuracy is untested.
          </Note>
        </div>
        <div style={{ position: "absolute", top: 250, left: 1010 }}>
          <ArtifactExcerpt id="recall" width={760} at={60} />
        </div>
      </Panel>
    </Sequence>
    <Labels kind="stored" local />
  </Shell>
);
