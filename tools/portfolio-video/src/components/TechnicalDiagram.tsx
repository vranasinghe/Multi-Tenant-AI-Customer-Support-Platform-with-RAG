import { useEffect, useState } from "react";
import { cancelRender, continueRender, delayRender, staticFile, useCurrentFrame } from "remotion";

import { mix, progress } from "../animations";

export type ViewBox = [number, number, number, number];

type Props = {
  /** File name in public/diagrams, copied from docs/portfolio-video/diagrams. */
  file: string;
  /** Frame at which each `step-N` layer appears, index 0 = step-1. */
  reveal: number[];
  width: number;
  height: number;
  viewBox?: ViewBox;
  zoomTo?: ViewBox;
  zoomAt?: number;
  zoomFrames?: number;
  /** Further camera moves, applied in order after `viewBox`. */
  camera?: { at: number; box: ViewBox; frames?: number }[];
  /** Grow bar rectangles from their baseline (charts). */
  growBars?: boolean;
};

/**
 * Animates the supplied SVG by its own layers. Labels, arrows and values are never rewritten: only
 * opacity, position, line drawing and the viewed region change. The heading group is hidden because
 * the video supplies its own title and evidence label; the footnote with the source stays.
 */
export const TechnicalDiagram = ({
  file,
  reveal,
  width,
  height,
  viewBox = [0, 0, 1920, 1080],
  zoomTo,
  zoomAt = 0,
  zoomFrames = 24,
  camera = [],
  growBars = false,
}: Props) => {
  const frame = useCurrentFrame();
  const [markup, setMarkup] = useState<string | null>(null);
  const [handle] = useState(() => delayRender(`diagram ${file}`));

  useEffect(() => {
    fetch(staticFile(`diagrams/${file}`))
      .then((response) => {
        if (!response.ok) throw new Error(`${file}: ${response.status}`);
        return response.text();
      })
      .then((text) => {
        const body = text
          .slice(text.indexOf("<svg"))
          // Solid connectors get a normalised length so they can be drawn.
          .replace(/<path (?![^>]*stroke-dasharray)([^>]*marker-end)/g, '<path pathLength="1" $1')
          .replace(/ width="1920" height="1080"/, ' width="100%" height="100%"');
        setMarkup(body);
        continueRender(handle);
      })
      .catch((error: unknown) => cancelRender(error));
  }, [file, handle]);

  if (markup === null) return null;

  const t = zoomTo ? progress(frame, zoomAt, zoomFrames) : 0;
  let box: number[] = viewBox.map((value, i) =>
    zoomTo ? mix(value, zoomTo[i] as number, t) : value,
  );
  for (const move of camera) {
    const p = progress(frame, move.at, move.frames ?? 30);
    box = box.map((value, i) => mix(value, move.box[i] as number, p));
  }
  const scope = `dg-${file.slice(0, 3)}`;
  const rules = reveal.map((at, index) => {
    const p = progress(frame, at, 12);
    const draw = progress(frame, at, 18);
    const layer = `.${scope} #step-${index + 1}`;
    const bars = growBars
      ? `${layer} > rect{transform-box:fill-box;transform-origin:bottom;transform:scaleY(${progress(frame, at, 20)})}`
      : "";
    return (
      `${layer}{opacity:${p};transform:translateY(${(1 - p) * 16}px)}` +
      `${layer} path[pathLength]{stroke-dasharray:1 1;stroke-dashoffset:${1 - draw}}${bars}`
    );
  });
  // Dashed connectors drift in their direction of travel.
  rules.push(
    `.${scope} [id^=step-] path[stroke-dasharray]:not([pathLength]){stroke-dashoffset:${-frame * 1.2}}`,
  );
  rules.push(`.${scope} #heading{display:none}`);

  return (
    <div className={scope} style={{ width, height }}>
      <style>{rules.join("")}</style>
      <div
        style={{ width: "100%", height: "100%" }}
        dangerouslySetInnerHTML={{
          __html: markup.replace(/viewBox="0 0 1920 1080"/, `viewBox="${box.join(" ")}"`),
        }}
      />
    </div>
  );
};
