import { Audio, Sequence, getStaticFiles, interpolate, staticFile } from "remotion";

const exists = (name: string) => getStaticFiles().some((file) => file.name === name);

/** Which audio the owner has supplied for a video. Nothing is generated or downloaded. */
export function audioFiles(video: "showcase" | "documentary") {
  const voice = `audio/${video}-voice.wav`;
  const music = `audio/${video}-music.wav`;
  // Music is used only when its licence is saved next to it.
  const licence = `audio/${video}-music.licence.txt`;
  const click = "audio/click.wav";
  return {
    voice: exists(voice) ? voice : null,
    music: exists(music) && exists(licence) ? music : null,
    click: exists(click) ? click : null,
  };
}

/** Three separate tracks: narration, music (ducked), interface sounds. */
export const AudioTracks = ({
  video,
  clicks,
  durationInFrames,
}: {
  video: "showcase" | "documentary";
  clicks: number[];
  durationInFrames: number;
}) => {
  const files = audioFiles(video);
  return (
    <>
      {files.voice ? (
        <Sequence name="Narration" layout="none">
          <Audio src={staticFile(files.voice)} />
        </Sequence>
      ) : null}
      {files.music ? (
        <Sequence name="Music" layout="none">
          <Audio
            src={staticFile(files.music)}
            loop
            volume={(frame) =>
              (files.voice ? 0.12 : 0.4) *
              interpolate(
                frame,
                [0, 30, durationInFrames - 45, durationInFrames - 1],
                [0, 1, 1, 0],
                {
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
                },
              )
            }
          />
        </Sequence>
      ) : null}
      {files.click
        ? clicks.map((frame) => (
            <Sequence
              key={frame}
              from={frame}
              durationInFrames={15}
              name="Interface sound"
              layout="none"
            >
              <Audio src={staticFile(files.click as string)} volume={0.25} />
            </Sequence>
          ))
        : null}
    </>
  );
};
