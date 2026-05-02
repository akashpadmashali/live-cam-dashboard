# Live Video Streaming

This project is now split into two parts:

1. A local Python backend that connects to your DroidCam feeds on the same Wi-Fi.
2. A static frontend dashboard that talks to that backend over HTTP.

That split is important because Cloudflare Pages can host the frontend later, but the backend still has to run on your laptop or another machine on your local network if the cameras only expose private IPs.

## Architecture

- **Phones / cameras**: DroidCam serves MJPEG feeds on your LAN.
- **Local backend**: FastAPI + OpenCV keeps one connection per camera, compresses frames to JPEG, and exposes APIs for config, camera status, and snapshots.
- **Frontend**: plain HTML/CSS/JS dashboard with editable camera settings.
- **Cloudflare Tunnel**: exposes the backend to the internet.
- **Cloudflare Pages (optional later)**: can host the frontend only.

## Project Layout

```text
app.py
scripts/
  start.sh
  stop.sh
  status.sh
frontend/
  index.html
  styles.css
  app.js
config.json
.env.example
requirements.txt
```

## Install

```bash
pip install -r requirements.txt
```

## Configure

The backend creates `config.json` automatically on first run using values from `.env` or `.env.example`.

Example `.env.example` values:

```bash
CAMERA_1_NAME=Front Door (Cam 1)
CAMERA_1_URL=http://10.107.109.21:4747/video

CAMERA_2_NAME=Backyard (Cam 2)
CAMERA_2_URL=http://192.168.30.138:4747/video

STREAM_MAX_WIDTH=640
STREAM_TARGET_FPS=4
UI_REFRESH_MS=400
STREAM_JPEG_QUALITY=70
APP_HOST=127.0.0.1
APP_PORT=8501
ALLOWED_ORIGINS=*
```

After the backend is running, you can edit camera names, IPs, and stream settings directly in the UI. Saving from the UI updates `config.json` and reloads the camera readers.

## Run Locally

```bash
python3 app.py
```

Open:

```text
http://127.0.0.1:8501
```

## Managed Local Run

You can also use the helper scripts to run the backend and a Quick Tunnel together:

```bash
chmod +x scripts/*.sh
./scripts/start.sh
```

Check status:

```bash
./scripts/status.sh
```

Stop everything:

```bash
./scripts/stop.sh
```

The scripts store PID files and logs in `.run/`.

## API

- `GET /api/health`
- `GET /api/config`
- `PUT /api/config`
- `GET /api/cameras`
- `GET /api/cameras/{camera_id}/frame.jpg`
- `GET /api/cameras/{camera_id}/stream.mjpg`

The frontend uses continuous MJPEG from the backend while keeping status polling separate. That avoids the visible flicker from swapping standalone JPEG snapshots every few hundred milliseconds.

## Cloudflare Quick Tunnel

Start the backend:

```bash
python3 app.py
```

Then expose it:

```bash
./.cloudflared-local/usr/bin/cloudflared tunnel --url http://127.0.0.1:8501
```

Use the generated `trycloudflare.com` URL for testing.

If you use the helper scripts, `./scripts/start.sh` already does both steps for you.

## GitHub + Cloudflare Pages Later

If you push this repo to GitHub, the recommended next step is:

1. Keep `app.py` running on your laptop or home server.
2. Deploy `frontend/` to Cloudflare Pages.
3. Point the frontend at your tunneled backend URL.
4. Keep camera IP access on the backend only.

That means your local machine still does the important origin work:

- reading local camera feeds
- resizing/compressing frames
- storing config
- serving the API the frontend calls

## Why This Is Better Than the Old Version

- The UI can edit camera IPs directly.
- The backend owns the LAN camera access.
- The frontend is portable and can later live on Pages.
- Browser-side config can point the frontend at a tunneled backend URL.
- Cloudflare Tunnel now exposes a more web-native backend instead of a continuously rerendering Streamlit session.

## Cloudflare Pages Setup

Yes, you can deploy the `frontend/` folder to Cloudflare Pages.

Suggested Pages settings:

- `Framework preset`: `None`
- `Build command`: `./scripts/build-pages.sh`
- `Build output directory`: `dist`
- `Production branch`: `main`

Optional Pages environment variable:

- `BACKEND_BASE_URL`

Example value:

```text
https://highways-stages-interesting-univ.trycloudflare.com
```

After deployment:

1. Open the Pages site URL.
2. If `BACKEND_BASE_URL` was set in Cloudflare, the frontend will use it automatically.
3. You can still override it manually in the `Backend Base URL` field and save from the UI.

The Pages-hosted frontend will call your tunneled backend for camera config, status, and MJPEG streams. Manual changes are stored in browser local storage, while the build-time variable gives you a sane default on first load.
