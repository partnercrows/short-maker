import sys
import time

from app.pipeline.active_speaker import pipeline as active_speaker_pipeline


def main(video_path: str) -> None:
    start = time.time()
    result = active_speaker_pipeline.run(video_path)
    elapsed = time.time() - start

    print(f"video: {video_path}")
    print(f"elapsed: {elapsed:.1f}s")
    print(f"available: {result.available}")
    print(f"reason: {result.reason}")
    print(f"num tracks: {len(result.track_trajectories)}")
    for track_id, samples in result.track_trajectories.items():
        print(f"  {track_id}: {len(samples)} samples")
    print(f"num segments: {len(result.segments)}")
    for seg in result.segments:
        print(f"  {seg.start:.2f}-{seg.end:.2f}  {seg.speaker_id}  conf={seg.confidence:.2f}")


if __name__ == "__main__":
    main(sys.argv[1])
