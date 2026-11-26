import { Composition, Folder } from "remotion";

import { ComponentGallery } from "./compositions/ComponentGallery";
import { DOCUMENTARY_FRAMES, EngineeringDocumentary } from "./compositions/EngineeringDocumentary";
import { PortfolioShowcaseV2, SHOWCASE_V2_FRAMES } from "./compositions/PortfolioShowcaseV2";
import {
  PortfolioShowcase,
  SHOWCASE_SCENE_COMPONENTS,
  type VideoProps,
} from "./compositions/PortfolioShowcase";
import { SHOWCASE_FRAMES, showcaseTimeline } from "./data/showcase";
import { FPS, HEIGHT, WIDTH } from "./styles/theme";

const size = { fps: FPS, width: WIDTH, height: HEIGHT };
const preview: VideoProps = { variant: "preview", captions: true };

export const Root = () => (
  <>
    <Composition
      id="EngineeringDocumentary"
      component={EngineeringDocumentary}
      durationInFrames={DOCUMENTARY_FRAMES}
      defaultProps={preview}
      {...size}
    />
    <Composition
      id="PortfolioShowcase"
      component={PortfolioShowcase}
      durationInFrames={SHOWCASE_FRAMES}
      defaultProps={preview}
      {...size}
    />
    <Composition
      id="PortfolioShowcaseV2"
      component={PortfolioShowcaseV2}
      durationInFrames={SHOWCASE_V2_FRAMES}
      defaultProps={preview}
      {...size}
    />
    <Folder name="Showcase-scenes">
      {showcaseTimeline.map((scene) => (
        <Composition
          key={scene.id}
          id={`Showcase-${scene.id}`}
          component={SHOWCASE_SCENE_COMPONENTS[scene.id]}
          durationInFrames={scene.frames}
          {...size}
        />
      ))}
    </Folder>
    <Composition
      id="ComponentGallery"
      component={ComponentGallery}
      durationInFrames={90}
      {...size}
    />
  </>
);
