/* ============================================================
   Software Update Tool — Mass Update screen (update.html)
   File selection, connection toggle, simulated deployment.
   ============================================================ */

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  /* ---------- Element references ---------- */

  const form = $("update-form");
  const fileInput = $("firmware-file");
  const filePathLabel = $("firmware-file-label");
  const fileMeta = $("firmware-file-meta");
  const dropZone = $("drop-zone");
  const connectButton = $("connect-button");
  const comPort = $("com-port");
  const startButton = $("start-button");
  const pauseButton = $("pause-button");
  const stopButton = $("stop-button");
  const clearLogsButton = $("clear-logs");
  const terminalLogs = $("terminal-logs");
  const passCountEl = $("pass-count");
  const failCountEl = $("fail-count");
  const progressTrack = $("progress-track");
  const progressBarFill = $("progress-bar-fill");
  const progressPercentage = $("progress-percentage");
  const speedInfo = $("speed-info");

  /* ---------- Constants & state ---------- */

  const TOTAL_DEVICES = 145;
  const FAILED_DEVICES = 3;
  const TICK_MS = 600;

  let isConnected = false;
  let timerId = null;
  let progress = 0;
  let succeeded = 0;

  /* ---------- Helpers ---------- */

  const formatFileSize = (bytes) =>
    bytes < 1024 * 1024
      ? `Size: ${(bytes / 1024).toFixed(1)} KB`
      : `Size: ${(bytes / (1024 * 1024)).toFixed(1)} MB`;

  const timestamp = () => {
    const now = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    return `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(
      now.getSeconds(),
    )}`;
  };

  const log = (level, message) => {
    const line = document.createElement("p");
    line.className = `log-line log-${level}`;
    line.textContent = `[${timestamp()}] ${level.toUpperCase()}: ${message}`;
    terminalLogs.appendChild(line);
    terminalLogs.scrollTop = terminalLogs.scrollHeight;
  };

  const setProgress = (value) => {
    progress = Math.min(100, Math.max(0, value));
    progressBarFill.style.width = `${progress}%`;
    progressPercentage.textContent = `${Math.round(progress)}%`;
    progressTrack.setAttribute("aria-valuenow", String(Math.round(progress)));

    if (progress >= 100) {
      speedInfo.textContent = "Update complete";
    } else {
      const remainingSeconds = Math.round(((100 - progress) / 100) * 60);
      speedInfo.textContent = `Estimated Time Remaining: ~${remainingSeconds} seconds`;
    }
  };

  const setSelectedFile = (file) => {
    if (!file) {
      return;
    }
    filePathLabel.textContent = file.name;
    fileMeta.textContent = formatFileSize(file.size);
  };

  /* ---------- File selection ---------- */

  fileInput.addEventListener("change", () =>
    setSelectedFile(fileInput.files[0]),
  );

  ["dragenter", "dragover"].forEach((eventName) =>
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.add("dragover");
    }),
  );

  ["dragleave", "drop"].forEach((eventName) =>
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.remove("dragover");
    }),
  );

  dropZone.addEventListener("drop", (event) => {
    const [file] = event.dataTransfer.files;
    if (!file) {
      return;
    }
    const transfer = new DataTransfer();
    transfer.items.add(file);
    fileInput.files = transfer.files;
    setSelectedFile(file);
  });

  /* ---------- Connection ---------- */

  const setConnected = (value) => {
    isConnected = value;
    connectButton.classList.toggle("is-connected", value);
    connectButton.textContent = value ? "Disconnect" : "Connect";
    comPort.disabled = value;
  };

  connectButton.addEventListener("click", () => {
    if (!isConnected && !comPort.value) {
      log("warning", "Cannot connect: no COM port selected.");
      comPort.focus();
      return;
    }
    setConnected(!isConnected);
    log(
      isConnected ? "success" : "info",
      isConnected
        ? `Connected to device on ${comPort.value}`
        : "Disconnected from device",
    );
  });

  /* ---------- Deployment simulation ---------- */

  const stopTimer = () => {
    if (timerId !== null) {
      clearInterval(timerId);
      timerId = null;
    }
  };

  const resetRunControls = () => {
    stopTimer();
    startButton.disabled = false;
    pauseButton.disabled = true;
    stopButton.disabled = true;
    pauseButton.textContent = "Pause";
    pauseButton.setAttribute("aria-pressed", "false");
  };

  const tick = () => {
    if (progress >= 100) {
      return;
    }

    setProgress(progress + 1 + Math.random() * 2);

    // Grow the succeeded count roughly in step with progress.
    const target = Math.round(
      (progress / 100) * (TOTAL_DEVICES - FAILED_DEVICES),
    );
    if (target > succeeded) {
      succeeded = target;
      passCountEl.textContent = String(succeeded);
    }

    if (Math.random() < 0.35) {
      const block = Math.max(1, Math.round((progress / 100) * 64));
      log(
        "process",
        `Flashing firmware block ${block}/64 to verified devices...`,
      );
    }

    if (progress >= 100) {
      passCountEl.textContent = String(TOTAL_DEVICES - FAILED_DEVICES);
      resetRunControls();
      log(
        "success",
        `Deployment complete: ${TOTAL_DEVICES - FAILED_DEVICES} succeeded, ${FAILED_DEVICES} failed.`,
      );
    }
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();

    if (!isConnected) {
      log("warning", "Cannot start: no device connected.");
      comPort.focus();
      return;
    }

    if (!fileInput.files.length) {
      log("warning", "Cannot start: no firmware file selected.");
      dropZone.scrollIntoView({ behavior: "smooth", block: "nearest" });
      return;
    }

    succeeded = 0;
    passCountEl.textContent = "0";
    failCountEl.textContent = String(FAILED_DEVICES);
    setProgress(0);

    startButton.disabled = true;
    pauseButton.disabled = false;
    stopButton.disabled = false;

    log(
      "info",
      `Starting firmware deployment to ${TOTAL_DEVICES} devices via ${comPort.value}...`,
    );
    timerId = setInterval(tick, TICK_MS);
  });

  pauseButton.addEventListener("click", () => {
    const resuming = pauseButton.textContent.trim() === "Resume";
    pauseButton.textContent = resuming ? "Pause" : "Resume";
    pauseButton.setAttribute("aria-pressed", String(!resuming));

    if (resuming) {
      timerId = setInterval(tick, TICK_MS);
      log("info", "Deployment resumed.");
    } else {
      stopTimer();
      log("warning", "Deployment paused by operator.");
    }
  });

  stopButton.addEventListener("click", () => {
    resetRunControls();
    setProgress(0);
    log("error", "Deployment aborted by operator.");
  });

  clearLogsButton.addEventListener("click", () => {
    terminalLogs.replaceChildren();
  });
})();
