"""One background thread per camera.

The thread:
  1. Opens the RTSP stream (auto-reconnects if it drops).
  2. Runs face recognition on ~PROCESS_FPS frames per second (not every frame — that
     would waste CPU and add no value).
  3. Draws boxes + names on the frame and keeps the latest JPEG in memory for the
     dashboard's MJPEG preview.
  4. Logs a debounced RecognitionEvent (with a snapshot crop) for the audit feed and
     the access decision.

`rtsp_url` also accepts a local video file path or webcam index string for testing
without a real camera (OpenCV's VideoCapture handles all three).
"""
import os
import threading
import time

import cv2
import numpy as np
import requests

from .. import config, settings_store
from ..database import SessionLocal
from ..models import Camera, RecognitionEvent
from ..recognition import engine, liveness
from ..recognition.gallery import gallery

FONT = cv2.FONT_HERSHEY_SIMPLEX


class CameraWorker(threading.Thread):
    def __init__(self, cam_id, name, rtsp_url, location=None):
        super().__init__(daemon=True)
        self.cam_id = cam_id
        self.name = name
        self.rtsp_url = rtsp_url
        self.location = location
        self._stop = threading.Event()
        self._latest_jpeg = None
        self._jpeg_lock = threading.Lock()
        self._latest_frame = None            # newest raw frame, handed to the recognition thread
        self._frame_lock = threading.Lock()
        self._detections = []                # cached [(box, label, color)] from the last pass
        self._det_lock = threading.Lock()
        self._last_logged = {}  # key(person_id or 'unknown') -> last event timestamp
        self.status = "starting"

    # --- lifecycle --------------------------------------------------------
    def stop(self):
        self._stop.set()

    def get_jpeg(self):
        with self._jpeg_lock:
            return self._latest_jpeg

    def _publish(self, frame):
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if ok:
            with self._jpeg_lock:
                self._latest_jpeg = buf.tobytes()

    # --- main loop --------------------------------------------------------
    def run(self):
        # Recognition is CPU-heavy (a few hundred ms per pass). Running it inline would
        # stall frame publishing and make the preview stutter, so it lives on its own
        # thread: the read loop below just grabs frames, overlays the boxes from the most
        # recent pass, and publishes — a smooth live feed even while inference is busy.
        infer = threading.Thread(target=self._infer_loop, daemon=True)
        infer.start()
        while not self._stop.is_set():
            cap = self._open()
            if cap is None:
                self.status = "reconnecting"
                self._set_latest(None)
                self._publish_placeholder("NO SIGNAL")
                time.sleep(3.0)
                continue

            self.status = "live"
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    self.status = "reconnecting"
                    self._set_latest(None)
                    break  # stream dropped -> reopen
                self._set_latest(frame)
                with self._det_lock:
                    dets = self._detections
                for box, label, color in dets:
                    self._draw(frame, box, label, color)
                self._draw_header(frame)
                self._publish(frame)
            cap.release()
            if not self._stop.is_set():
                time.sleep(2.0)  # brief backoff before reconnecting
        self.status = "stopped"

    def _set_latest(self, frame):
        # Store a clean copy so the recognition thread never reads the annotated preview
        # frame and the two threads never mutate the same array. Clearing on None also
        # drops stale boxes when the stream drops.
        with self._frame_lock:
            self._latest_frame = None if frame is None else frame.copy()
        if frame is None:
            with self._det_lock:
                self._detections = []

    def _infer_loop(self):
        """Continuously recognize the latest frame at ~PROCESS_FPS, off the preview path."""
        interval = 1.0 / max(config.PROCESS_FPS, 0.5)
        while not self._stop.is_set():
            time.sleep(interval)
            with self._frame_lock:
                frame = self._latest_frame
                self._latest_frame = None  # consume; don't reprocess the same frame
            if frame is None:
                continue
            try:
                dets = self._recognize(frame)
                with self._det_lock:
                    self._detections = dets
            except Exception as exc:  # never let recognition kill the worker
                print(f"[cam {self.cam_id}] recognition error: {exc}")

    def _open(self):
        cap = cv2.VideoCapture(self.rtsp_url)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # keep latency low
        except Exception:
            pass
        if not cap.isOpened():
            cap.release()
            return None
        return cap

    # --- recognition ------------------------------------------------------
    def _recognize(self, frame):
        """Detect + match every face. Returns [(box, label, color)] for the preview to
        overlay, and logs a debounced event per decision. Runs on the inference thread."""
        results = []
        for face in engine.detect_faces(frame):
            box = face.bbox.astype(int)
            if engine.face_size(face) < config.MIN_FACE_PIXELS:
                results.append((box, "", (120, 120, 120)))  # too small/far to trust
                continue

            match = gallery.match(face.normed_embedding)
            live = liveness.is_live(frame, face)

            if match and match["active"] and live:
                decision, color = "granted", (0, 200, 0)
                key = match["person_id"]
                pid, pname, sim = match["person_id"], match["name"], match["similarity"]
                label = f'{pname}  {sim * 100:.0f}%'
            elif match and not match["active"]:
                decision, color = "denied", (0, 140, 255)
                key = match["person_id"]
                pid, pname, sim = match["person_id"], match["name"], match["similarity"]
                label = f'{pname} (INACTIVE)'
            elif match and not live:
                decision, color = "denied", (0, 0, 255)
                key = f'spoof-{match["person_id"]}'
                pid, pname, sim = match["person_id"], match["name"], match["similarity"]
                label = f'{pname} (SPOOF?)'
            else:
                decision, color = "denied", (0, 0, 255)
                key = "unknown"
                pid, pname, sim = None, None, (match["similarity"] if match else None)
                label = "UNKNOWN"

            results.append((box, label, color))
            self._maybe_log(key, pid, pname, sim, decision, frame, box)
        return results

    def _maybe_log(self, key, pid, pname, sim, decision, frame, box):
        if key == "unknown" and not settings_store.get_bool("log_unknown", config.LOG_UNKNOWN):
            return
        now = time.time()
        if now - self._last_logged.get(key, 0.0) < config.EVENT_DEBOUNCE_SECONDS:
            return
        self._last_logged[key] = now

        snap_name = self._save_snapshot(frame, box, now)
        db = SessionLocal()
        try:
            db.add(
                RecognitionEvent(
                    camera_id=self.cam_id,
                    person_id=pid,
                    person_name=pname,
                    similarity=sim,
                    decision=decision,
                    snapshot=snap_name,
                )
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            print(f"[cam {self.cam_id}] failed to log event: {exc}")
        finally:
            db.close()

        if decision == "granted":
            self._fire_access_webhook(pid, pname, sim)

    def _fire_access_webhook(self, pid, pname, sim):
        """POST to a door-relay/webhook when access is granted (fire-and-forget).

        Typically points at a relay board on the LAN, e.g. http://192.168.1.30/relay/on —
        so it stays on-premises and offline.
        """
        url = settings_store.get("access_webhook_url", "") or ""
        if not url:
            return
        payload = {
            "event": "access_granted",
            "person_id": pid,
            "person_name": pname,
            "camera_id": self.cam_id,
            "camera_name": self.name,
            "similarity": sim,
        }

        def _post():
            try:
                requests.post(url, json=payload, timeout=2)
            except Exception as exc:
                print(f"[cam {self.cam_id}] webhook failed: {exc}")

        threading.Thread(target=_post, daemon=True).start()

    def _save_snapshot(self, frame, box, ts):
        try:
            x1, y1, x2, y2 = box
            crop = frame[max(0, y1): max(0, y2), max(0, x1): max(0, x2)]
            if crop.size == 0:
                return None
            os.makedirs(config.SNAPSHOT_DIR, exist_ok=True)
            name = f"cam{self.cam_id}_{int(ts * 1000)}.jpg"
            cv2.imwrite(os.path.join(config.SNAPSHOT_DIR, name), crop)
            return name
        except Exception:
            return None

    # --- drawing ----------------------------------------------------------
    def _draw(self, frame, box, label, color):
        x1, y1, x2, y2 = box
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        if label:
            cv2.rectangle(frame, (x1, y1 - 22), (x2, y1), color, -1)
            cv2.putText(frame, label, (x1 + 4, y1 - 6), FONT, 0.5, (0, 0, 0), 1)

    def _draw_header(self, frame):
        text = f"{self.name}  -  {self.status}"
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 24), (0, 0, 0), -1)
        cv2.putText(frame, text, (8, 17), FONT, 0.55, (255, 255, 255), 1)

    def _publish_placeholder(self, text):
        img = np.zeros((360, 640, 3), dtype=np.uint8)
        cv2.putText(img, f"{self.name}: {text}", (20, 190), FONT, 0.9, (0, 0, 255), 2)
        self._publish(img)


class CameraManager:
    """Starts/stops CameraWorkers and maps camera_id -> worker."""

    def __init__(self):
        self._workers: dict[int, CameraWorker] = {}
        self._lock = threading.Lock()

    def start_camera(self, cam: Camera):
        with self._lock:
            if cam.id in self._workers:
                return
            worker = CameraWorker(cam.id, cam.name, cam.rtsp_url, cam.location)
            worker.start()
            self._workers[cam.id] = worker

    def stop_camera(self, cam_id: int):
        with self._lock:
            worker = self._workers.pop(cam_id, None)
        if worker:
            worker.stop()

    def restart_camera(self, cam: Camera):
        self.stop_camera(cam.id)
        time.sleep(0.2)
        self.start_camera(cam)

    def get_worker(self, cam_id: int):
        return self._workers.get(cam_id)

    def start_all_enabled(self):
        db = SessionLocal()
        try:
            for cam in db.query(Camera).filter(Camera.enabled.is_(True)).all():
                self.start_camera(cam)
        finally:
            db.close()

    def stop_all(self):
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for worker in workers:
            worker.stop()


# Singleton used by the API + app lifespan.
manager = CameraManager()
