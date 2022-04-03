#!/usr/bin/env python3

from functools import partial
import sys
from typing import DefaultDict
from cv2 import undistortPoints
import numpy as np
from camera_calibration import (
    get_calibration_params,
    to_camera_coords,
)
from frontend.method import create_frontend
from visualization.tracking import create_drawer_thread
from frontend.frame import create_frame
from frontend.optical_flow import (
    create_lk_orb_detector,
    track_to_new_frame,
)
from frontend.video import Video
from geometry import (
    create_point_triangulator,
    epipolar_ransac,
)
from visualization.mapping import create_map_thread
from utils.worker import create_thread_context
from threading import current_thread

np.set_printoptions(precision=3, suppress=True)


if __name__ == "__main__":
    video_path = sys.argv[1]
    video = Video(video_path)
    width, height = video.width, video.height

    thread_context = create_thread_context()
    send_draw_task = create_drawer_thread(thread_context)

    video_stream = video.get_video_stream()
    K, Kinv, d = get_calibration_params()
    undistort = lambda kp: undistortPoints(kp, K, d, R=np.eye(3), P=K).squeeze()
    detector = create_lk_orb_detector(undistort)
    tracker = track_to_new_frame
    epipolar_localizer = partial(epipolar_ransac,K)
    frontend = create_frontend(
        detector,
        tracker,
        epipolar_localizer,
        undistort,
    )
    triangulation = create_point_triangulator(K)
    send_map_task = create_map_thread(
        (800, 600),
        Kinv,
        (width, height),
        thread_context,
    )
    thread_context.start()

    frames = video_stream
    tracked_frames = []
    map_points = []
    last_keyframe = None
    for image in frames:
        frame = create_frame(len(tracked_frames), image)
        frame = frontend(frame)
        if frame is None:
            continue
        tracked_frames += [frame]
        if frame.is_keyframe:
            candidate_pts = [
                lm
                for lm in frame.observations
                if not lm.is_initialized and len(lm.idxs) > 1
            ]
            matches = DefaultDict(lambda: [[], []])
            for lm in candidate_pts:
                id, idx = next(x for x in lm.idxs.items())
                curr_idx = next(reversed(lm.idxs.values()))
                ref_idxs, curr_idxs = matches[id]
                ref_idxs += [idx]
                curr_idxs += [curr_idx]
            for f_id, (ref_idxs, curr_idxs) in matches.items():
                ref_idxs = np.array(ref_idxs)
                curr_idxs = np.array(curr_idxs)
                pts_3d, good_pts = triangulation(
                    frame.pose,
                    tracked_frames[f_id].pose,
                    frame.undist[curr_idxs],
                    tracked_frames[f_id].undist[ref_idxs],
                )
                for i, pt in zip(curr_idxs[good_pts], pts_3d[good_pts]):
                    to_idx = lambda kp: tuple(np.rint(kp).astype(int)[::-1])
                    landmark = frame.observations[i]
                    landmark.coords = pt
                    img_idx = to_idx(frame.key_pts[i])
                    landmark.color = frame.image[img_idx] / 255.0
                    landmark.is_initialized = True
                    map_points += [landmark]

        send_draw_task(tracked_frames)
        send_map_task(tracked_frames, map_points)
        if thread_context.is_closed:
            break
    thread_context.wait_close()
    thread_context.cleanup()
    thread_context.join_all()
    print(f"{current_thread()} exiting.")
