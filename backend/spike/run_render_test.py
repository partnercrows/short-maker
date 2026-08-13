import sys
import time

import cv2

from app.pipeline.reframe.modes import resolve
from app.pipeline.reframe.models import ReframeMode
from app.pipeline.render import render


def main(video_path: str, output_path: str) -> None:
    cap = cv2.VideoCapture(video_path)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    start = time.time()
    plan = resolve(
        video_path=video_path,
        requested_mode=ReframeMode.AUTO,
        source_width=w,
        source_height=h,
        target_width=720,
        target_height=1280,
    )
    print(f"resolve: {time.time() - start:.1f}s  mode_used={plan.mode_used}  windows={len(plan.windows)}")

    start = time.time()
    render(video_path, plan, output_path, 720, 1280)
    print(f"render: {time.time() - start:.1f}s -> {output_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
