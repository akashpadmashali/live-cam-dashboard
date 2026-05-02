import atexit
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

import cv2
import uvicorn
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
FRONTEND_DIR = BASE_DIR / "frontend"


def load_env_file(path: str) -> None:
    """Load KEY=VALUE pairs from a simple .env-style file."""
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key and key not in os.environ:
                os.environ[key] = value


def get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default

    try:
        return int(value)
    except ValueError:
        return default


def get_float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if not value:
        return default

    try:
        return float(value)
    except ValueError:
        return default


def slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


def load_default_config() -> dict[str, Any]:
    load_env_file(".env")
    load_env_file(".env.example")

    cameras = []
    index = 1
    while True:
        name = os.getenv(f"CAMERA_{index}_NAME")
        url = os.getenv(f"CAMERA_{index}_URL")
        if not name or not url:
            break

        cameras.append(
            {
                "id": f"camera-{index}",
                "name": name,
                "url": url,
            }
        )
        index += 1

    if not cameras:
        cameras = [
            {
                "id": "camera-1",
                "name": "Front Door (Cam 1)",
                "url": "http://192.168.1.101:4747/video",
            },
            {
                "id": "camera-2",
                "name": "Backyard (Cam 2)",
                "url": "http://192.168.1.102:4747/video",
            },
        ]

    return {
        "server": {
            "host": os.getenv("APP_HOST", "127.0.0.1"),
            "port": get_int_env("APP_PORT", 8501),
            "allowed_origins": os.getenv("ALLOWED_ORIGINS", "*"),
        },
        "stream": {
            "max_width": get_int_env("STREAM_MAX_WIDTH", 640),
            "target_fps": get_float_env("STREAM_TARGET_FPS", 4.0),
            "ui_refresh_ms": get_int_env("UI_REFRESH_MS", 500),
            "jpeg_quality": get_int_env("STREAM_JPEG_QUALITY", 70),
        },
        "cameras": cameras,
    }


def load_config() -> dict[str, Any]:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as config_file:
            return json.load(config_file)

    config = load_default_config()
    save_config(config)
    return config


def save_config(config: dict[str, Any]) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as config_file:
        json.dump(config, config_file, indent=2)


class CameraInput(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1)
    url: str = Field(min_length=1)


class StreamSettingsInput(BaseModel):
    max_width: int = Field(default=640, ge=160, le=1920)
    target_fps: float = Field(default=4.0, ge=0.5, le=30)
    ui_refresh_ms: int = Field(default=500, ge=100, le=5000)
    jpeg_quality: int = Field(default=70, ge=30, le=95)


class ConfigInput(BaseModel):
    cameras: list[CameraInput]
    stream: StreamSettingsInput


class CameraStream:
    """Keep a single shared connection per camera and cache the latest frame."""

    def __init__(
        self,
        camera_id: str,
        name: str,
        url: str,
        max_width: int,
        target_fps: float,
        jpeg_quality: int,
    ) -> None:
        self.camera_id = camera_id
        self.name = name
        self.url = url
        self.max_width = max_width
        self.target_fps = target_fps
        self.jpeg_quality = jpeg_quality
        self.lock = threading.Lock()
        self.frame_jpeg: bytes | None = None
        self.status = "Connecting"
        self.failures = 0
        self.last_frame_at = 0.0
        self.running = True
        self.thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.thread.start()

    def _reader_loop(self) -> None:
        capture = None

        while self.running:
            if capture is None or not capture.isOpened():
                if capture is not None:
                    capture.release()

                capture = cv2.VideoCapture(self.url)
                capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                if not capture.isOpened():
                    with self.lock:
                        self.failures += 1
                        self.status = f"Reconnect attempt {self.failures}"
                    time.sleep(1)
                    continue

            ok, frame = capture.read()
            if ok:
                frame = self._resize_frame(frame)
                success, encoded = cv2.imencode(
                    ".jpg",
                    frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
                )
                if success:
                    with self.lock:
                        self.frame_jpeg = encoded.tobytes()
                        self.status = "Live"
                        self.failures = 0
                        self.last_frame_at = time.time()
                time.sleep(1 / self.target_fps)
            else:
                with self.lock:
                    self.failures += 1
                    self.status = f"Reconnect attempt {self.failures}"
                capture.release()
                capture = None
                time.sleep(1)

        if capture is not None:
            capture.release()

    def _resize_frame(self, frame):
        height, width = frame.shape[:2]
        if width <= self.max_width:
            return frame

        scale = self.max_width / width
        new_size = (self.max_width, max(1, int(height * scale)))
        return cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)

    def snapshot(self) -> tuple[bytes | None, str, float]:
        with self.lock:
            return self.frame_jpeg, self.status, self.last_frame_at

    def stop(self) -> None:
        self.running = False
        self.thread.join(timeout=2)


class CameraManager:
    def __init__(self, config: dict[str, Any]) -> None:
        self.lock = threading.Lock()
        self.config = config
        self.streams: dict[str, CameraStream] = {}
        self._load_streams()

    def _load_streams(self) -> None:
        stream_settings = self.config["stream"]
        self.streams = {}
        for index, camera in enumerate(self.config["cameras"], start=1):
            camera_id = camera.get("id") or f"camera-{index}"
            self.streams[camera_id] = CameraStream(
                camera_id=camera_id,
                name=camera["name"],
                url=camera["url"],
                max_width=stream_settings["max_width"],
                target_fps=stream_settings["target_fps"],
                jpeg_quality=stream_settings["jpeg_quality"],
            )

    def get_config(self) -> dict[str, Any]:
        with self.lock:
            return json.loads(json.dumps(self.config))

    def reload(self, config: dict[str, Any]) -> None:
        with self.lock:
            old_streams = list(self.streams.values())
            self.config = config
            self._load_streams()

        for stream in old_streams:
            stream.stop()

    def list_cameras(self) -> list[dict[str, Any]]:
        config = self.get_config()
        cameras = []
        for camera in config["cameras"]:
            stream = self.streams.get(camera["id"])
            status = "Not started"
            last_frame_at = 0.0
            if stream is not None:
                _, status, last_frame_at = stream.snapshot()
            cameras.append(
                {
                    "id": camera["id"],
                    "name": camera["name"],
                    "url": camera["url"],
                    "status": status,
                    "last_frame_at": last_frame_at,
                }
            )
        return cameras

    def get_frame(self, camera_id: str) -> bytes | None:
        stream = self.streams.get(camera_id)
        if stream is None:
            return None

        frame, _, _ = stream.snapshot()
        return frame

    def get_stream_state(self, camera_id: str) -> tuple[bytes | None, str, float] | None:
        stream = self.streams.get(camera_id)
        if stream is None:
            return None
        return stream.snapshot()

    def stop(self) -> None:
        for stream in self.streams.values():
            stream.stop()


app = FastAPI(title="Live Video Streaming Control Plane")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


def get_manager() -> CameraManager:
    manager = getattr(app.state, "camera_manager", None)
    if manager is None:
        raise RuntimeError("Camera manager not initialized")
    return manager


@app.on_event("startup")
def startup_event() -> None:
    config = load_config()
    allowed_origins = config["server"]["allowed_origins"]
    app.state.allowed_origins = allowed_origins
    app.state.camera_manager = CameraManager(config)
    atexit.register(app.state.camera_manager.stop)


@app.on_event("shutdown")
def shutdown_event() -> None:
    manager = getattr(app.state, "camera_manager", None)
    if manager is not None:
        manager.stop()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def get_config_endpoint() -> dict[str, Any]:
    return get_manager().get_config()


@app.put("/api/config")
def update_config(payload: ConfigInput) -> dict[str, Any]:
    manager = get_manager()
    cameras = []
    used_ids = set()

    for index, camera in enumerate(payload.cameras, start=1):
        fallback_id = f"camera-{index}"
        camera_id = camera.id or slugify(camera.name, fallback_id)
        if camera_id in used_ids:
            camera_id = f"{camera_id}-{index}"
        used_ids.add(camera_id)
        cameras.append(
            {
                "id": camera_id,
                "name": camera.name,
                "url": camera.url,
            }
        )

    config = manager.get_config()
    config["cameras"] = cameras
    config["stream"] = payload.stream.model_dump()
    save_config(config)
    manager.reload(config)
    return config


@app.get("/api/cameras")
def list_cameras_endpoint() -> list[dict[str, Any]]:
    return get_manager().list_cameras()


@app.get("/api/cameras/{camera_id}/frame.jpg")
def camera_frame(camera_id: str) -> Response:
    frame = get_manager().get_frame(camera_id)
    if frame is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    if not frame:
        raise HTTPException(status_code=503, detail="Frame not available yet")
    return Response(content=frame, media_type="image/jpeg")


def mjpeg_generator(camera_id: str):
    last_frame_at = 0.0
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"

    while True:
        state = get_manager().get_stream_state(camera_id)
        if state is None:
            break

        frame, _, frame_time = state
        if frame and frame_time != last_frame_at:
            last_frame_at = frame_time
            yield boundary + frame + b"\r\n"

        time.sleep(0.05)


@app.get("/api/cameras/{camera_id}/stream.mjpg")
def camera_stream(camera_id: str) -> StreamingResponse:
    state = get_manager().get_stream_state(camera_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    return StreamingResponse(
        mjpeg_generator(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/{full_path:path}")
def frontend(full_path: str) -> FileResponse:
    target = FRONTEND_DIR / full_path
    if full_path and target.exists() and target.is_file():
        return FileResponse(target)
    return FileResponse(FRONTEND_DIR / "index.html")


def main() -> None:
    current_config = load_config()
    uvicorn.run(
        app,
        host=current_config["server"]["host"],
        port=current_config["server"]["port"],
        reload=False,
    )


if __name__ == "__main__":
    main()
