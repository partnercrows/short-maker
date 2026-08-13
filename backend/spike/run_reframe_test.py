import sys
import time

import cv2

from app.pipeline.reframe.modes import resolve
from app.pipeline.reframe.models import ReframeMode


def main(video_path: str) -> None:
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
    elapsed = time.time() - start

    print(f"video: {video_path} ({w}x{h})")
    print(f"elapsed: {elapsed:.1f}s")
    print(f"mode_used: {plan.mode_used}")
    print(f"fallback_reason: {plan.fallback_reason}")
    print(f"num windows: {len(plan.windows)}")
    if plan.windows:
        xs = [win.x for win in plan.windows]
        print(f"x range: {min(xs)}-{max(xs)}  (crop size {plan.windows[0].width}x{plan.windows[0].height})")
        # print a sparse sample of the trajectory
        step = max(1, len(plan.windows) // 20)
        for win in plan.windows[::step]:
            print(f"  t={win.time:.2f}  x={win.x}")


if __name__ == "__main__":
    main(sys.argv[1])
