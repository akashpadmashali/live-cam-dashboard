const configForm = document.getElementById("config-form");
const cameraList = document.getElementById("camera-list");
const cameraGrid = document.getElementById("camera-grid");
const addCameraButton = document.getElementById("add-camera");
const saveStatus = document.getElementById("save-status");
const cameraFormTemplate = document.getElementById("camera-form-template");
const cameraCardTemplate = document.getElementById("camera-card-template");

const maxWidthInput = document.getElementById("max-width");
const targetFpsInput = document.getElementById("target-fps");
const uiRefreshInput = document.getElementById("ui-refresh");
const jpegQualityInput = document.getElementById("jpeg-quality");
const apiBaseUrlInput = document.getElementById("api-base-url");

let currentRefreshMs = 500;
const cameraCards = new Map();

function getApiBaseUrl() {
  return (localStorage.getItem("edge_api_base_url") || "").trim().replace(/\/$/, "");
}

function setApiBaseUrl(value) {
  const normalized = value.trim().replace(/\/$/, "");
  if (normalized) {
    localStorage.setItem("edge_api_base_url", normalized);
  } else {
    localStorage.removeItem("edge_api_base_url");
  }
}

function apiUrl(path) {
  const base = getApiBaseUrl();
  return base ? `${base}${path}` : path;
}

function createCameraForm(camera = { name: "", url: "" }) {
  const fragment = cameraFormTemplate.content.cloneNode(true);
  const editor = fragment.querySelector(".camera-editor");
  const title = fragment.querySelector(".camera-title");
  const nameInput = fragment.querySelector(".camera-name");
  const urlInput = fragment.querySelector(".camera-url");
  const removeButton = fragment.querySelector(".remove-camera");

  nameInput.value = camera.name || "";
  urlInput.value = camera.url || "";
  title.textContent = camera.name || "New Camera";

  nameInput.addEventListener("input", () => {
    title.textContent = nameInput.value.trim() || "New Camera";
  });

  removeButton.addEventListener("click", () => {
    editor.remove();
  });

  return fragment;
}

function renderCameraForms(cameras) {
  cameraList.innerHTML = "";
  cameras.forEach((camera) => {
    cameraList.appendChild(createCameraForm(camera));
  });
}

function buildPayload() {
  const cameraEditors = [...cameraList.querySelectorAll(".camera-editor")];
  return {
    cameras: cameraEditors
      .map((editor) => ({
        name: editor.querySelector(".camera-name").value.trim(),
        url: editor.querySelector(".camera-url").value.trim(),
      }))
      .filter((camera) => camera.name && camera.url),
    stream: {
      max_width: Number(maxWidthInput.value),
      target_fps: Number(targetFpsInput.value),
      ui_refresh_ms: Number(uiRefreshInput.value),
      jpeg_quality: Number(jpegQualityInput.value),
    },
  };
}

async function loadConfig() {
  const response = await fetch(apiUrl("/api/config"));
  const config = await response.json();

  apiBaseUrlInput.value = getApiBaseUrl();
  renderCameraForms(config.cameras);
  maxWidthInput.value = config.stream.max_width;
  targetFpsInput.value = config.stream.target_fps;
  uiRefreshInput.value = config.stream.ui_refresh_ms;
  jpegQualityInput.value = config.stream.jpeg_quality;
  currentRefreshMs = config.stream.ui_refresh_ms;
}

function createCameraCard(camera) {
  const fragment = cameraCardTemplate.content.cloneNode(true);
  const card = fragment.querySelector(".camera-card");
  const name = fragment.querySelector(".card-name");
  const url = fragment.querySelector(".card-url");
  const statusBadge = fragment.querySelector(".status-badge");
  const frame = fragment.querySelector(".camera-frame");
  const fallback = fragment.querySelector(".frame-fallback");

  name.textContent = camera.name;
  url.textContent = camera.url;
  frame.alt = camera.name;

  frame.src = apiUrl(`/api/cameras/${camera.id}/stream.mjpg`);
  frame.onload = () => {
    frame.classList.add("ready");
    fallback.style.display = "none";
  };
  frame.onerror = () => {
    fallback.style.display = "grid";
    fallback.textContent = "Stream reconnecting...";
  };

  card.dataset.cameraId = camera.id;
  const cardState = { fragment, card, statusBadge, fallback, frame, name, url };
  updateCameraCard(cardState, camera);
  return cardState;
}

function updateCameraCard(cardState, camera) {
  const { card, name, url, statusBadge, fallback, frame } = cardState;
  card.dataset.cameraId = camera.id;
  name.textContent = camera.name;
  url.textContent = camera.url;
  frame.alt = camera.name;

  if (camera.status === "Live") {
    statusBadge.textContent = "Live";
    statusBadge.classList.add("live");
    if (frame.classList.contains("ready")) {
      fallback.style.display = "none";
    }
  } else {
    statusBadge.textContent = camera.status;
    statusBadge.classList.remove("live");
    if (!frame.classList.contains("ready")) {
      fallback.style.display = "grid";
      fallback.textContent = camera.status;
    }
  }
}

function syncCameraCards(cameras) {
  const seenIds = new Set();

  cameras.forEach((camera) => {
    seenIds.add(camera.id);
    const existing = cameraCards.get(camera.id);
    if (existing) {
      updateCameraCard(existing, camera);
      return;
    }

    const cardState = createCameraCard(camera);
    cameraCards.set(camera.id, cardState);
    cameraGrid.appendChild(cardState.fragment);
  });

  [...cameraCards.keys()].forEach((cameraId) => {
    if (seenIds.has(cameraId)) {
      return;
    }

    const cardState = cameraCards.get(cameraId);
    cardState.card.remove();
    cameraCards.delete(cameraId);
  });
}

async function refreshStatuses() {
  try {
    const response = await fetch(apiUrl("/api/cameras"));
    const cameras = await response.json();
    syncCameraCards(cameras);
  } catch (error) {
    console.error(error);
  } finally {
    window.setTimeout(refreshStatuses, currentRefreshMs);
  }
}

addCameraButton.addEventListener("click", () => {
  cameraList.appendChild(createCameraForm());
});

configForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  saveStatus.textContent = "Saving...";

  try {
    setApiBaseUrl(apiBaseUrlInput.value);
    const payload = buildPayload();
    const response = await fetch(apiUrl("/api/config"), {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error("Failed to save config");
    }

    const config = await response.json();
    currentRefreshMs = config.stream.ui_refresh_ms;
    cameraCards.clear();
    cameraGrid.innerHTML = "";
    saveStatus.textContent = "Saved. Streams are reconnecting with the new config.";
    await loadConfig();
    await refreshStatuses();
  } catch (error) {
    console.error(error);
    saveStatus.textContent = "Could not save config. Check the values and try again.";
  }
});

async function bootstrap() {
  apiBaseUrlInput.value = getApiBaseUrl();
  await loadConfig();
  await refreshStatuses();
}

bootstrap();
