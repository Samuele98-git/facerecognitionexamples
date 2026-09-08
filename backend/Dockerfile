# Python 3.12 base — the ML wheels (onnxruntime/insightface) don't build on 3.14 yet.
FROM python:3.12-slim

# System libs: build tools for insightface's cython bits, OpenCV runtime deps, ffmpeg for RTSP.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# Install build deps first, then everything with build isolation OFF so insightface's
# source build can see numpy/cython (otherwise its setup.py fails to import numpy).
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir numpy==1.26.4 cython \
    && pip install --no-cache-dir --no-build-isolation -r requirements.txt

# Auth deps in a separate layer so adding them doesn't invalidate the (slow) ML layer above.
RUN pip install --no-cache-dir "PyJWT==2.10.1" "bcrypt==4.2.1"

# Flush logs immediately so startup/model messages show up in `docker compose logs`.
ENV PYTHONUNBUFFERED=1

# Bundle the pre-downloaded face model INTO the image so the system runs FULLY OFFLINE.
# Placed BEFORE the app copy so ordinary code changes don't re-copy the 325MB model.
COPY models/buffalo_l /root/.insightface/models/buffalo_l

# Anti-spoofing (liveness) ONNX models, also baked in for fully-offline operation.
COPY models/antispoof /app/antispoof_models

# App code changes most often -> keep it last so only this thin layer rebuilds.
COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
