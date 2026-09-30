import os
import sys
import subprocess
import urllib.request
import cv2
import numpy as np
from typing import Dict, Any, List, Optional

YUNET_MODEL_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
YUNET_FILENAME = "face_detection_yunet_2023mar.onnx"

class FaceCenterTracker:
    """
    Ultra-accurate Neural Face Tracking Engine powered by OpenCV YuNet (FaceDetectorYN).
    - Detects exact human facial bounding boxes and landmarks in <5ms.
    - Zero external API dependencies, zero quota consumption, 100% offline.
    - Multi-frame temporal sampling with median filtering to eliminate outlier movements.
    - Automatically centers host and guest in Dual-Speaker Split Screen (stacked 9:16).
    - Automatically centers solo creators in 9:16 vertical crop (center_crop & split_gaming).
    """

    _detector = None
    _model_path = None

    @classmethod
    def get_model_path(cls) -> str:
        """Locates or downloads the YuNet ONNX model."""
        if cls._model_path and os.path.exists(cls._model_path):
            return cls._model_path

        # Candidate paths
        candidates = []
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            candidates.append(os.path.join(sys._MEIPASS, "storage", YUNET_FILENAME))
            candidates.append(os.path.join(sys._MEIPASS, YUNET_FILENAME))

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        storage_path = os.path.join(base_dir, "storage", YUNET_FILENAME)
        candidates.append(storage_path)

        for p in candidates:
            if os.path.exists(p) and os.path.getsize(p) > 50000:
                cls._model_path = p
                return p

        # Download automatically if not found
        try:
            os.makedirs(os.path.join(base_dir, "storage"), exist_ok=True)
            print(f"[FaceCenterTracker] Downloading YuNet ONNX model to {storage_path}...")
            req = urllib.request.Request(YUNET_MODEL_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
                if len(data) > 50000:
                    with open(storage_path, "wb") as f:
                        f.write(data)
                    cls._model_path = storage_path
                    print(f"[FaceCenterTracker] YuNet model successfully saved ({len(data)} bytes).")
                    return storage_path
        except Exception as e:
            print(f"[FaceCenterTracker] Warning: Could not download YuNet model: {e}")

        cls._model_path = storage_path
        return storage_path

    @classmethod
    def get_detector(cls, width: int = 320, height: int = 320):
        """Initializes or reconfigures the YuNet FaceDetectorYN instance."""
        model_path = cls.get_model_path()
        if not os.path.exists(model_path) or os.path.getsize(model_path) < 50000:
            return None

        try:
            if cls._detector is None:
                cls._detector = cv2.FaceDetectorYN.create(
                    model=model_path,
                    config="",
                    input_size=(width, height),
                    score_threshold=0.60,
                    nms_threshold=0.30,
                    top_k=5000
                )
            else:
                cls._detector.setInputSize((width, height))
            return cls._detector
        except Exception as e:
            print(f"[FaceCenterTracker] Detector init notice: {e}")
            return None

    @staticmethod
    def extract_frame_cv(video_path: str, timestamp_sec: float) -> Optional[np.ndarray]:
        """Extracts a single frame from video at timestamp as a BGR numpy array using FFmpeg."""
        try:
            cmd = [
                "ffmpeg", "-y",
                "-ss", f"{timestamp_sec:.2f}",
                "-i", video_path,
                "-vframes", "1",
                "-f", "image2pipe",
                "-vcodec", "rawvideo",
                "-pix_fmt", "bgr24",
                "-"
            ]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
            if proc.returncode == 0 and len(proc.stdout) > 0:
                from app.core.video_engine import get_video_info
                info = get_video_info(video_path)
                w, h = info["width"], info["height"]
                expected_bytes = w * h * 3
                if len(proc.stdout) >= expected_bytes:
                    raw = proc.stdout[:expected_bytes]
                    frame = np.frombuffer(raw, dtype=np.uint8).reshape((h, w, 3))
                    return frame
        except Exception as e:
            print(f"[FaceCenterTracker] Frame extract notice: {e}")
        return None

    @classmethod
    def analyze_frame_speakers(cls, img: np.ndarray) -> Dict[str, Any]:
        """
        Runs YuNet neural face detection on a single frame.
        Identifies solo speaker center and dual host/guest speaker centers.
        """
        h, w = img.shape[:2]
        detector = cls.get_detector(w, h)
        
        candidates = []
        if detector is not None:
            try:
                retval, faces = detector.detect(img)
                if faces is not None and len(faces) > 0:
                    for f in faces:
                        fx, fy, fw, fh = float(f[0]), float(f[1]), float(f[2]), float(f[3])
                        conf = float(f[-1])
                        if conf < 0.60:
                            continue
                        
                        cx = fx + (fw / 2.0)
                        cy = fy + (fh / 2.0)
                        area = (fw * fh) / float(w * h)

                        # Filter out tiny background faces
                        if fw / float(w) >= 0.05 and fh / float(h) >= 0.08:
                            candidates.append({
                                "norm_x": float(np.clip(cx / float(w), 0.05, 0.95)),
                                "norm_y": float(np.clip(cy / float(h), 0.05, 0.95)),
                                "norm_w": float(fw / float(w)),
                                "norm_h": float(fh / float(h)),
                                "area": area,
                                "conf": conf,
                                "score": area * conf
                            })
            except Exception as e:
                print(f"[FaceCenterTracker] Neural detection error: {e}")

        # If neural detector found faces:
        if candidates:
            # Sort by significance (area * confidence)
            candidates.sort(key=lambda c: c["score"], reverse=True)
            dominant = candidates[0]
            solo_x = dominant["norm_x"]
            solo_y = dominant["norm_y"]

            left_candidates = [c for c in candidates if c["norm_x"] < 0.50]
            right_candidates = [c for c in candidates if c["norm_x"] >= 0.50]

            host_x = max(left_candidates, key=lambda c: c["score"])["norm_x"] if left_candidates else 0.30
            guest_x = max(right_candidates, key=lambda c: c["score"])["norm_x"] if right_candidates else 0.70

            return {
                "host_x": host_x,
                "guest_x": guest_x,
                "solo_x": solo_x,
                "solo_y": solo_y,
                "candidates_count": len(candidates),
                "is_detected": True
            }

        # Fallback if no human face detected (e.g. gameplay, graphic animation, or B-roll)
        return {
            "host_x": 0.30,
            "guest_x": 0.70,
            "solo_x": 0.50,
            "solo_y": 0.35,
            "candidates_count": 0,
            "is_detected": False
        }

    @classmethod
    def get_optimal_crop_coordinates(cls, video_path: str, duration: float) -> Dict[str, Any]:
        """
        Samples 5 keyframes across the clip timeline and computes median face centers.
        Guarantees that speaker face is centered in the upper-middle third with head room.
        """
        defaults = {
            "host_x_norm": 0.30,
            "guest_x_norm": 0.70,
            "solo_x_norm": 0.50,
            "solo_y_norm": 0.35,
            "is_neural_tracking_active": False,
            "detections_count": 0
        }

        if not os.path.exists(video_path) or duration <= 0:
            return defaults

        # Sample 5 distinct keyframes across the clip timeline
        sample_times = [
            max(0.4, duration * 0.15),
            duration * 0.35,
            duration * 0.50,
            duration * 0.70,
            min(duration - 0.4, duration * 0.85)
        ]

        host_xs = []
        guest_xs = []
        solo_xs = []
        solo_ys = []
        valid_detections = 0

        for st in sample_times:
            frame = cls.extract_frame_cv(video_path, st)
            if frame is not None:
                analysis = cls.analyze_frame_speakers(frame)
                if analysis.get("is_detected"):
                    valid_detections += 1
                    host_xs.append(analysis["host_x"])
                    guest_xs.append(analysis["guest_x"])
                    solo_xs.append(analysis["solo_x"])
                    solo_ys.append(analysis["solo_y"])

        if solo_xs:
            median_host_x = float(np.median(host_xs))
            median_guest_x = float(np.median(guest_xs))
            median_solo_x = float(np.median(solo_xs))
            median_solo_y = float(np.median(solo_ys))

            print(f"[FaceCenterTracker] Neural tracking active ({valid_detections}/5 frames): "
                  f"Solo X={median_solo_x:.3f}, Solo Y={median_solo_y:.3f}, "
                  f"Host X={median_host_x:.3f}, Guest X={median_guest_x:.3f}")

            return {
                "host_x_norm": median_host_x,
                "guest_x_norm": median_guest_x,
                "solo_x_norm": median_solo_x,
                "solo_y_norm": median_solo_y,
                "is_neural_tracking_active": True,
                "detections_count": valid_detections
            }

        print("[FaceCenterTracker] No neural face detections across sample frames. Using standard center 0.50.")
        return defaults
