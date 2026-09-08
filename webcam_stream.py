#!/usr/bin/env python3
"""Publish this PC's webcam as an MJPEG stream over HTTP, so the face-recognition
backend (running in Docker, which can't see USB/integrated cameras on Windows) can
read it like an ordinary IP camera.

Run on the HOST (not inside Docker):
    python webcam_stream.py                 # camera 0, port 8090
    python webcam_stream.py --camera 1      # pick a different camera
    python webcam_stream.py --port 8091     # pick a different port

Then in the dashboard's Cameras tab, add a camera with this URL:
    http://host.docker.internal:8090/video

Stop it with Ctrl+C. A background grabber thread keeps only the latest frame, so the
camera is read once regardless of how many things connect.
"""
import argparse
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

BOUNDARY = "frame"
_latest = {"frame": None}
_lock = threading.Lock()
_stop = threading.Event()


def _grabber(cap):
    while not _stop.is_set():
        ok, frame = cap.read()
        if ok and frame is not None:
            with _lock:
                _latest["frame"] = frame
        else:
            time.sleep(0.03)


def _make_handler(quality):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):  # keep the console quiet
            pass

        def do_GET(self):
            if self.path.rstrip("/") in ("", "/health"):
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"ok - MJPEG stream at /video\n")
                return
            if not self.path.startswith("/video"):
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header(
                "Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}"
            )
            self.end_headers()
            try:
                while not _stop.is_set():
                    with _lock:
                        frame = _latest["frame"]
                    if frame is None:
                        time.sleep(0.03)
                        continue
                    ok, jpg = cv2.imencode(
                        ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality]
                    )
                    if not ok:
                        continue
                    data = jpg.tobytes()
                    self.wfile.write(b"--" + BOUNDARY.encode() + b"\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(
                        b"Content-Length: " + str(len(data)).encode() + b"\r\n\r\n"
                    )
                    self.wfile.write(data)
                    self.wfile.write(b"\r\n")
                    time.sleep(0.04)  # ~25 fps cap
            except (BrokenPipeError, ConnectionResetError):
                pass  # client (backend or browser) went away

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--camera", type=int, default=0, help="webcam index (default 0)")
    ap.add_argument("--port", type=int, default=8090, help="HTTP port (default 8090)")
    ap.add_argument("--quality", type=int, default=80, help="JPEG quality 1-100")
    args = ap.parse_args()

    # CAP_DSHOW is the most reliable capture backend for webcams on Windows.
    cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(args.camera)  # fall back to the default backend
    if not cap.isOpened():
        print(f"ERROR: could not open camera index {args.camera}.", file=sys.stderr)
        print("Try a different --camera index, or close apps using the camera.", file=sys.stderr)
        sys.exit(1)

    for _ in range(5):  # let auto-exposure settle
        cap.read()

    threading.Thread(target=_grabber, args=(cap,), daemon=True).start()

    print(f"Webcam {args.camera} streaming on http://0.0.0.0:{args.port}/video")
    print(f"In the dashboard, add a camera with URL:")
    print(f"    http://host.docker.internal:{args.port}/video")
    print("Press Ctrl+C to stop.")

    server = ThreadingHTTPServer(("0.0.0.0", args.port), _make_handler(args.quality))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _stop.set()
        cap.release()
        server.server_close()


if __name__ == "__main__":
    main()
