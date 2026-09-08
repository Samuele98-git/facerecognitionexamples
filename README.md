# Face Access Control

Real-time face recognition for a company entrance, using your existing IP cameras.
Dashboard shows every camera live, the AI matches faces against enrolled employees at
different angles, and you add/remove people on hire/fire with **no model retraining**.

---

## How it actually works (the important idea)

Modern face recognition does **not** "learn people." A pre-trained model (`buffalo_l` —
ArcFace, trained on 17M faces) turns any face into a 512-number **embedding** ("fingerprint").

- **Enroll a person** = store their photo's embedding.
- **Recognize** = embed the face on the camera, compare (cosine similarity) to the stored
  embeddings, best score above a threshold wins.
- **Hire/fire** = insert/delete an embedding, or flip an `active` flag. **Instant. No training.**

Accuracy in "all conditions" comes from: the pre-trained model + enrolling **several angles
per person** + a **calibrated threshold** + decent camera placement — not from training.
See [`ml/DATASETS.md`](ml/DATASETS.md).

> ℹ️ **iPhone Face ID vs cameras:** Face ID uses a 3D depth sensor up close. IP cameras are
> 2D at a distance, so you can't replicate its depth-based anti-spoofing — but ArcFace hits
> 99.8%+ on benchmarks and is what real access systems use. For spoof resistance (someone
> holding up a photo) wire in the liveness model (`backend/app/recognition/liveness.py`).

> 🛡️ **Anti-spoofing built in.** Enable **liveness** in Settings to reject printed photos and
> phone/tablet screens (MiniFASNet, runs offline). See "Liveness" below.

> 🔒 **Fully offline.** Detection, embeddings, liveness, and matching all run locally via ONNX Runtime.
> The model is **baked into the Docker image** — no cloud API, no telemetry, nothing leaves
> the machine at runtime. The *only* online step is fetching the model file once (below);
> after that the system is air-gappable.

## Architecture

```
IP cameras ──RTSP──> Camera workers (OpenCV) ──> InsightFace detect+embed ──> Gallery match
                            │                                                      │
                            ▼                                                      ▼
                     MJPEG preview                                       RecognitionEvent (audit)
                            │                                                      │
                            └───────────────► FastAPI ◄────────────────────────────┘
                                                 │
                                          React dashboard
                                    (grid · feed · enroll · cameras)
```

- **Backend:** FastAPI + SQLAlchemy (SQLite by default, PostgreSQL in Docker)
- **AI:** InsightFace `buffalo_l` (SCRFD detector + ResNet100 ArcFace) on ONNX Runtime
- **Frontend:** React + Vite
- **Matching:** in-memory NumPy cosine (swap for FAISS/Qdrant at large scale)

## Prerequisites

Already on this machine: **Docker**, **Node 24**, **git**. (Local Python is 3.14, which the
ML wheels don't support yet — that's why the backend runs in Docker on Python 3.12.)

## Run it

### 0. Fetch the model once (the only online step)

On a machine with internet, download + extract the face model into `backend/models/buffalo_l`:

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File scripts/fetch_model.ps1
```
```bash
# Linux / macOS
bash scripts/fetch_model.sh
```

This is the **only** time anything touches the internet. The model then gets baked into the
Docker image, so every later build/run is fully offline (air-gappable). For a truly
disconnected server, build the image on a connected machine and move it with
`docker save` / `docker load`.

### 1. Backend + database (Docker)

```bash
docker compose up --build
```

When you see `recognition model ready`, the API is up at **http://localhost:8000**
(docs at http://localhost:8000/docs, health at http://localhost:8000/api/health — check
`"model_ready": true`).

### 2. Dashboard (local Node)

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. The dev server proxies `/api` and `/media` to the backend.

## Using it

0. **Sign in** at http://localhost:5173. On first boot an **admin** account is created; if you
   didn't set `ADMIN_PASSWORD`, the generated password is printed once in `docker compose logs
   backend` (look for "INITIAL ADMIN ACCOUNT CREATED"). Change it under **Settings → Users**.
1. **People tab** → add a person → upload **3–5 photos from different angles** (front,
   ¾ left/right, slight up/down). The system rejects photos with zero or multiple faces.
2. **Cameras tab** → add a camera with its **RTSP URL**
   (e.g. `rtsp://user:pass@192.168.1.50:554/Streaming/Channels/101`). It starts immediately.
3. **Dashboard tab** → live grid with boxes/names, plus a recognition feed:
   - 🟢 **granted** — active enrolled person matched
   - 🔴 **denied** — unknown face, or an **inactive** (fired) person
4. **Fire someone:** toggle them to *Inactive* (keeps the audit trail) or Delete. Access is
   revoked on the next frame.

### No camera handy? Test with a video file
`rtsp_url` also accepts a local video path or webcam index (OpenCV opens all three). In
Docker, mount a clip and use its container path, or run [MediaMTX](https://github.com/bluenviron/mediamtx)
to publish a file/webcam as a real `rtsp://` stream.

## Tuning accuracy → your "99%+" target

1. Download **LFW** (and **CFP-FP** for angles) — see [`ml/DATASETS.md`](ml/DATASETS.md).
2. Calibrate the threshold:
   ```bash
   docker compose run --rm -v ${PWD}/ml:/ml backend \
     python /ml/benchmark.py --lfw-dir /ml/datasets/lfw --pairs /ml/datasets/pairs.txt
   ```
   It prints accuracy + **FAR** (impostor accepted — dangerous for a door) and **FRR**
   (genuine rejected) per threshold. For an entrance, pick a threshold with near-zero FAR.
3. Set `RECOGNITION_THRESHOLD` in `docker-compose.yml` (default `0.45`).
4. Enroll more angles per person; place cameras where faces are ~frontal and well-lit at the
   door; ensure enough face pixels (raise `DET_SIZE` for smaller/farther faces).

## Liveness / anti-spoofing

A 2D camera alone can be fooled by a printed photo or a phone screen showing an enrolled
person's face. Liveness closes that gap. It uses **Silent-Face MiniFASNet** (two small models),
converted to ONNX and **baked into the image** — 100% offline, no PyTorch at runtime. See
`scripts/liveness/` for the exact, self-verifying conversion (weights load strictly; ONNX
matches PyTorch to ~1e-6).

- **Enable it:** Settings → *Liveness / anti-spoofing* → toggle on, set the threshold.
- **How it acts:** a face that matches an enrolled person but fails liveness is **denied** and
  flagged `SPOOF?` in the feed — so a photo of an employee won't open the door.
- **Tuning:** higher threshold = stricter. Calibrate with real vs. printed/screen tests from
  your own cameras (lighting/distance matter). Off by default until you enable it.

## Configuration

All via environment (`docker-compose.yml` or `.env` — see `.env.example`): `RECOGNITION_THRESHOLD`,
`PROCESS_FPS`, `DET_SIZE`, `MIN_FACE_PIXELS`, `EVENT_DEBOUNCE_SECONDS`, `LOG_UNKNOWN`,
`USE_GPU`, `LIVENESS_ENABLED`.

## Scaling & production roadmap

- [ ] **GPU** for many cameras — `onnxruntime-gpu` + `USE_GPU=true` (needs NVIDIA Container Toolkit)
- [ ] **WebRTC** low-latency preview via [go2rtc](https://github.com/AlexxIT/go2rtc) instead of MJPEG
- [ ] **Liveness/anti-spoofing** — wire in [Silent-Face](https://github.com/minivision-ai/Silent-Face-Anti-Spoofing)
- [ ] **FAISS/Qdrant** vector index when people > a few thousand
- [x] **Auth** — login, bcrypt passwords, httpOnly+SameSite JWT cookies, roles, lockout (see below)
- [x] **Door hardware** — webhook fired on `granted` (configure the URL in Settings)
- [x] **Liveness/anti-spoofing** — MiniFASNet (ONNX, offline); enable in **Settings**
- [ ] **TLS** in front of the app, then set `COOKIE_SECURE=true`
- [ ] Optional **fine-tuning** on your own camera footage (the only place a rented GPU helps)

## Authentication & security

- **Login required** for everything — all data endpoints, the live camera streams, and the
  face images (`/api/media/...`) are gated. Only `/api/ping` is public.
- **Passwords**: bcrypt (with a sha256+base64 pre-hash so length/null bytes are safe).
- **Sessions**: HS256 JWT in an **httpOnly** cookie (JS/XSS can't read it) with
  **SameSite=strict** (blocks cross-site/CSRF). Set `COOKIE_SECURE=true` behind HTTPS.
- **Brute force**: per-account lockout (`MAX_FAILED_ATTEMPTS`/`LOCKOUT_MINUTES`) + per-IP rate
  limiting; login returns a generic error to prevent username enumeration.
- **Roles**: `admin` (manage users + settings) and `operator` (run the system).
- **Signing secret**: auto-generated and persisted on first boot, or set `JWT_SECRET`.

## Data

Biometric templates stay on-prem (your DB/`media` volume). `data/` is git-ignored so you never
commit faces. Encrypt the DB and `media` volume at rest, keep the app behind TLS, and retain the
`events` audit log. Consent is already collected from staff.

## Project layout

```
backend/
  app/
    config.py            env-driven settings
    database.py models.py schemas.py
    recognition/         engine (InsightFace), gallery (matching), liveness (stub)
    ingest/              camera_worker (RTSP threads + MJPEG) + manager
    routers/             people, cameras, events
    main.py              app wiring + startup
  Dockerfile requirements.txt
frontend/                React + Vite dashboard
ml/
  benchmark.py           threshold calibration on LFW/CFP-FP
  DATASETS.md            what to download and why (no training!)
docker-compose.yml .env.example
```
