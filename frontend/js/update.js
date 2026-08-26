/* ============================================================
   Software Update Tool — Mass Update screen (update.js)
   Real mode  : talks to the Python backend through pywebview
                (window.pywebview.api) + pushed events.
   Simulation : falls back to a local demo when opened in a
                plain browser without the backend.
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
  const browseLabel = dropZone.querySelector(".browse-button");
  const connectButton = $("connect-button");
  const refreshPortsButton = $("refresh-ports-button");
  const backButton = $("back-button");
  const comPort = $("com-port");
  const toolButtons = Array.from(document.querySelectorAll(".tool-btn"));
  const expectedFw = $("expected-fw");
  const startButton = $("start-button");
  const pauseButton = $("pause-button");
  const stopButton = $("stop-button");
  const clearLogsButton = $("clear-logs");
  const terminalLogs = $("terminal-logs");
  const updateResultEl = $("update-result");
  const fwCheckResultEl = $("fw-check-result");
  const fwDetectedEl = $("fw-detected");
  const statIcons = Array.from(
    document.querySelectorAll(".status-cards-row .stat-icon"),
  );
  const progressTrack = $("progress-track");
  const progressBarFill = $("progress-bar-fill");
  const progressPercentage = $("progress-percentage");
  const speedInfo = $("speed-info");
  const statusIndicator = document.querySelector(
    ".screen-header .status-indicator",
  );
  const statusText = statusIndicator.querySelector(".status-text");

  // Update guide modal ("How to get CSV file?")
  const guideOverlay = $("guide-overlay");
  const guideOpenButton = $("open-guide");
  const guideCloseButton = guideOverlay
    ? guideOverlay.querySelector("[data-close-guide]")
    : null;

  /* ---------- Constants & state ---------- */

  const TICK_MS = 600;

  const state = {
    connected: false,
    file: null, // { path, name, size, ext } | browser File wrapper
    toolType: "M12",
    running: false,
    paused: false,
    // simulation-only state
    timerId: null,
    progress: 0,
    simExpectedFw: "",
  };

  /* ---------- Generic helpers ---------- */

  const timestamp = () => {
    const now = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    return `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(
      now.getSeconds(),
    )}`;
  };

  const formatFileSize = (bytes) =>
    bytes < 1024 * 1024
      ? `${(bytes / 1024).toFixed(1)} KB`
      : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;

  function appendLog(level, message) {
    const line = document.createElement("p");
    line.className = `log-line log-${level}`;
    line.textContent = `[${timestamp()}] ${message}`;
    terminalLogs.appendChild(line);
    terminalLogs.scrollTop = terminalLogs.scrollHeight;
  }

  function classifyLevel(message) {
    if (/SUCCESS|PASS\b|verified/i.test(message)) return "success";
    if (/ERROR|FAIL\b|Traceback|aborted|mismatch/i.test(message))
      return "error";
    if (/WARNING|WARN\b|TIMEOUT|no response/i.test(message)) return "warning";
    if (/PROCESS|Flashing|block \d/i.test(message)) return "process";
    return "info";
  }

  function setProgress(value) {
    const clamped = Math.min(100, Math.max(0, value));
    progressBarFill.style.width = `${clamped}%`;
    progressPercentage.textContent = `${Math.round(clamped)}%`;
    progressTrack.setAttribute("aria-valuenow", String(Math.round(clamped)));
  }

  function setConnectedUI(connected, port) {
    state.connected = connected;
    connectButton.classList.toggle("is-connected", connected);
    connectButton.textContent = connected ? "Disconnect" : "Connect";
    comPort.disabled = connected;
    statusIndicator.classList.toggle("offline", !connected);
    statusText.textContent = connected
      ? port
        ? `Connected: ${port}`
        : "System Connected"
      : "Not Connected";
  }

  function setFileInfo(file) {
    state.file = file;
    filePathLabel.textContent = file.name;
    fileMeta.textContent = `Size: ${formatFileSize(
      file.size || 0,
    )} · ${(file.ext || "").toUpperCase() || "FILE"}`;
  }

  function resetResultCards() {
    updateResultEl.textContent = "…";
    updateResultEl.className = "stat-value";
    fwCheckResultEl.textContent = "…";
    fwCheckResultEl.className = "stat-value";
    fwDetectedEl.textContent = "Detected: —";
    if (statIcons[0]) statIcons[0].className = "stat-icon pass";
    if (statIcons[1]) statIcons[1].className = "stat-icon fail";
  }

  function handleFinished(res) {
    endRunUI();

    const ok = res.status === "PASS";
    const check = res.fwCheck || {};

    updateResultEl.textContent = ok ? "PASS" : "FAIL";
    updateResultEl.className = `stat-value ${ok ? "pass" : "fail"}`;
    if (statIcons[0]) {
      statIcons[0].className = `stat-icon ${ok ? "pass" : "fail"}`;
    }

    if (check.pass === true) {
      fwCheckResultEl.textContent = "PASS";
      fwCheckResultEl.className = "stat-value pass";
      if (statIcons[1]) statIcons[1].className = "stat-icon pass";
    } else if (check.pass === false) {
      fwCheckResultEl.textContent = "FAIL";
      fwCheckResultEl.className = "stat-value fail";
      if (statIcons[1]) statIcons[1].className = "stat-icon fail";
    } else {
      fwCheckResultEl.textContent = "SKIPPED";
      fwCheckResultEl.className = "stat-value";
    }

    fwDetectedEl.textContent = `Detected: ${
      check.detected ?? "—"
    }${check.expected ? ` · Expected: ${check.expected}` : ""}`;

    // The FW version check is independent of the update result: a failed
    // comparison is reported here (and in the FW card) without flipping
    // UPDATE RESULT to FAIL.
    if (ok && check.pass === false) {
      appendLog(
        "warning",
        `WARNING: FW version check FAILED - detected ${
          check.detected ?? "?"
        }${check.expected ? `, expected ${check.expected}` : ""}`,
      );
    }

    setProgress(ok ? 100 : 0);

    if (ok) {
      appendLog("success", "=== UPDATE FINISHED: PASS ===");
    } else {
      appendLog(
        "error",
        `=== UPDATE FINISHED: FAIL — ${res.reason || "unknown"} ===`,
      );
    }
  }

  /* ---------- Run control UI ---------- */

  function beginRun() {
    state.running = true;
    state.paused = false;
    startButton.disabled = true;
    pauseButton.disabled = false;
    pauseButton.textContent = "Pause";
    pauseButton.setAttribute("aria-pressed", "false");
    stopButton.disabled = false;
    resetResultCards();
    setProgress(0);
    speedInfo.textContent = "Preparing update...";
  }

  function endRunUI() {
    state.running = false;
    state.paused = false;
    startButton.disabled = false;
    pauseButton.disabled = true;
    pauseButton.textContent = "Pause";
    pauseButton.setAttribute("aria-pressed", "false");
    stopButton.disabled = true;
  }

  /* ============================================================
     Backend (pywebview) mode
     ============================================================ */

  async function refreshPorts() {
    try {
      const r = await Bridge.api.get_ports();
      if (r.status !== "SUCCESS") {
        appendLog(
          "warning",
          `Could not scan COM ports: ${r.message || "unknown error"}`,
        );
        return;
      }
      const ports = r.ports || [];
      const previousSelection = comPort.value;

      comPort.replaceChildren();
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.disabled = true;
      placeholder.selected = true;
      placeholder.textContent = ports.length
        ? "Select COM Port..."
        : "No COM ports found";
      comPort.appendChild(placeholder);
      ports.forEach((p) => {
        const option = document.createElement("option");
        option.value = p.port;
        option.textContent = `${p.port} — ${p.description}`;
        comPort.appendChild(option);
      });

      // Keep the previous selection when the port is still present
      if (
        previousSelection &&
        ports.some((p) => p.port === previousSelection)
      ) {
        comPort.value = previousSelection;
      }

      appendLog("info", `Found ${ports.length} COM port(s).`);
      if (!ports.length) {
        appendLog("warning", "No COM ports found on this system.");
      }
    } catch (err) {
      appendLog("error", `COM port scan failed: ${err.message}`);
    }
  }

  async function pickFileBackend() {
    try {
      const r = await Bridge.api.select_file();
      if (r.status === "SUCCESS") {
        setFileInfo(r);
        appendLog("info", `Selected file: ${r.path}`);
      } else if (r.status === "ERROR") {
        appendLog("error", r.message || "File selection failed");
      }
    } catch (err) {
      appendLog("error", `File dialog failed: ${err.message}`);
    }
  }

  async function onStart() {
    const fw = expectedFw.value.trim();

    if (!state.file) {
      appendLog("warning", "Cannot start: no .bin / .csv file selected.");
      dropZone.scrollIntoView({ behavior: "smooth", block: "nearest" });
      return;
    }
    if (fw && !/^\d+(\.\d+){0,3}$/.test(fw)) {
      appendLog(
        "warning",
        "Invalid FW version format — use decimal numbers separated by dots, e.g. 1.4.2",
      );
      expectedFw.focus();
      return;
    }
    if (!state.connected) {
      appendLog("warning", "Cannot start: no device connected.");
      comPort.focus();
      return;
    }

    beginRun();

    try {
      const r = await Bridge.api.run_update(
        state.file.path,
        state.toolType,
        fw,
      );
      if (r.status === "ERROR") {
        appendLog("error", r.message || "Failed to start update");
        endRunUI();
      }
      // Completion arrives asynchronously via onUpdateFinished.
    } catch (err) {
      appendLog("error", `Update failed to start: ${err.message}`);
      endRunUI();
    }
  }

  /* ============================================================
     Simulation mode (plain browser fallback)
     ============================================================ */

  function stopTimer() {
    if (state.timerId !== null) {
      clearInterval(state.timerId);
      state.timerId = null;
    }
  }

  function simulateTick() {
    if (state.progress >= 100) return;

    setProgress(state.progress + 1 + Math.random() * 2);

    const remainingSeconds = Math.round(((100 - state.progress) / 100) * 60);
    speedInfo.textContent =
      state.progress >= 100
        ? "Update complete"
        : `Estimated Time Remaining: ~${remainingSeconds} seconds`;

    if (Math.random() < 0.35) {
      const block = Math.max(1, Math.round((state.progress / 100) * 64));
      appendLog(
        "process",
        `[SIM] Flashing firmware block ${block}/64 to verified devices...`,
      );
    }

    if (state.progress >= 100) {
      stopTimer();
      finishSimulation();
    }
  }

  function simulateFwCheck(expected) {
    if (!expected) return null;
    const segments = expected.split(".").map(Number);
    const mismatch = Math.random() < 0.25;
    if (mismatch) {
      segments[segments.length - 1] += 1;
    }
    return {
      detected: `${segments.join(".")}.0`,
      pass: !mismatch,
    };
  }

  function finishSimulation() {
    const check = simulateFwCheck(state.simExpectedFw);

    // All simulated commands completed -> the update itself PASSES.
    // The FW version comparison keeps its own independent result.
    handleFinished({
      status: "PASS",
      reason: "",
      fwCheck: check
        ? {
            pass: check.pass,
            detected: check.detected,
            expected: state.simExpectedFw || null,
          }
        : null,
    });
  }

  function simulateRun(expectedFwValue) {
    state.simExpectedFw = expectedFwValue;
    state.progress = 0;
    setProgress(0);
    appendLog(
      "info",
      `[SIM] Starting simulated update of ${state.file.name} (${state.toolType})...`,
    );
    state.timerId = setInterval(simulateTick, TICK_MS);
  }

  /* ============================================================
     Event wiring
     ============================================================ */

  // ---- Events pushed from Python (registered up-front) ----

  Bridge.on("onLogFromPy", (message) => {
    const msg = String(message);
    appendLog(classifyLevel(msg), msg);
  });

  Bridge.on("onProgressFromPy", (percent, current, total) => {
    setProgress(percent);
    speedInfo.textContent =
      current != null && total != null
        ? `${current}/${total} commands`
        : "Working...";
  });

  Bridge.on("onUpdateFinished", (res) => handleFinished(res || {}));

  Bridge.on("onConnectionState", (st) =>
    setConnectedUI(!!(st && st.connected), st ? st.port : null),
  );

  // ---- Static DOM events ----

  function wireStaticEvents() {
    // Connection
    connectButton.addEventListener("click", async () => {
      if (Bridge.available) {
        connectButton.disabled = true;
        try {
          if (!state.connected) {
            if (!comPort.value) {
              appendLog("warning", "Cannot connect: no COM port selected.");
              comPort.focus();
              return;
            }
            const r = await Bridge.api.connect_port(comPort.value);
            if (r.status !== "SUCCESS") {
              appendLog("error", r.message || "Connection failed");
            }
          } else {
            await Bridge.api.disconnect_port();
          }
        } catch (err) {
          appendLog("error", `Connection error: ${err.message}`);
        } finally {
          connectButton.disabled = false;
        }
      } else {
        // Simulation toggle
        if (!state.connected && !comPort.value) {
          appendLog("warning", "Cannot connect: no COM port selected.");
          comPort.focus();
          return;
        }
        const port = comPort.value || "COM3 (simulated)";
        setConnectedUI(!state.connected, port);
        appendLog(
          state.connected ? "success" : "info",
          state.connected
            ? `[SIM] Connected to device on ${port}`
            : "[SIM] Disconnected from device",
        );
      }
    });

    // Back button ("Main Menu"): disconnect the COM port before leaving.
    // When not connected the link behaves normally.
    backButton.addEventListener("click", async (event) => {
      if (!state.connected) return;

      event.preventDefault();
      backButton.style.pointerEvents = "none"; // guard against double clicks
      try {
        if (Bridge.available) {
          if (state.running) {
            appendLog("warning", "Update aborted - returning to Main Menu...");
            await Bridge.api.stop_update();
          }
          await Bridge.api.disconnect_port();
        }
      } catch (err) {
        appendLog("error", `Disconnect failed: ${err.message}`);
      } finally {
        window.location.href = backButton.href;
      }
    });

    // Refresh COM port list
    refreshPortsButton.addEventListener("click", async () => {
      refreshPortsButton.disabled = true;
      refreshPortsButton.classList.add("is-spinning");
      try {
        if (Bridge.available) {
          await refreshPorts();
        } else {
          appendLog("info", "[SIM] COM port list refreshed.");
        }
      } finally {
        refreshPortsButton.classList.remove("is-spinning");
        refreshPortsButton.disabled = false;
      }
    });

    // Tool type selector
    toolButtons.forEach((button) =>
      button.addEventListener("click", () => {
        toolButtons.forEach((b) => {
          const active = b === button;
          b.classList.toggle("is-active", active);
          b.setAttribute("aria-pressed", String(active));
        });
        state.toolType = button.dataset.tool;
      }),
    );

    // Browse: use the native OS dialog when the backend is available
    browseLabel.addEventListener("click", (event) => {
      if (Bridge.available) {
        event.preventDefault();
        pickFileBackend();
      }
    });

    // Hidden input (browser / simulation mode only)
    fileInput.addEventListener("change", () => {
      if (Bridge.available) return;
      const file = fileInput.files[0];
      if (!file) return;
      const ext = file.name.split(".").pop().toLowerCase();
      setFileInfo({ path: null, name: file.name, size: file.size, ext });
    });

    // Drag & drop
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
      if (Bridge.available) {
        appendLog(
          "info",
          "Drag & drop can't provide the file path inside the desktop app — please use the Browse button.",
        );
        return;
      }
      const [file] = event.dataTransfer.files;
      if (!file) return;
      const ext = file.name.split(".").pop().toLowerCase();
      setFileInfo({ path: null, name: file.name, size: file.size, ext });
    });

    // Start
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      onStart();
    });

    // Pause / Resume
    pauseButton.addEventListener("click", async () => {
      if (!state.running) return;

      if (Bridge.available) {
        pauseButton.disabled = true;
        try {
          if (!state.paused) {
            await Bridge.api.pause_update();
            state.paused = true;
            pauseButton.textContent = "Resume";
            pauseButton.setAttribute("aria-pressed", "true");
          } else {
            await Bridge.api.resume_update();
            state.paused = false;
            pauseButton.textContent = "Pause";
            pauseButton.setAttribute("aria-pressed", "false");
          }
        } catch (err) {
          appendLog("error", `Pause/resume failed: ${err.message}`);
        } finally {
          pauseButton.disabled = false;
        }
      } else {
        const resuming = pauseButton.textContent.trim() === "Resume";
        pauseButton.textContent = resuming ? "Pause" : "Resume";
        pauseButton.setAttribute("aria-pressed", String(!resuming));
        if (resuming) {
          state.timerId = setInterval(simulateTick, TICK_MS);
          appendLog("info", "[SIM] Deployment resumed.");
        } else {
          stopTimer();
          appendLog("warning", "[SIM] Deployment paused by operator.");
        }
      }
    });

    // Stop
    stopButton.addEventListener("click", async () => {
      if (!state.running) return;

      if (Bridge.available) {
        stopButton.disabled = true;
        try {
          await Bridge.api.stop_update();
          // Final FAIL result arrives via onUpdateFinished.
        } catch (err) {
          appendLog("error", `Stop failed: ${err.message}`);
          stopButton.disabled = false;
        }
      } else {
        stopTimer();
        appendLog("error", "[SIM] Deployment aborted by operator.");
        handleFinished({
          status: "FAIL",
          reason: "Aborted by operator",
          fwCheck: null,
        });
      }
    });

    // Clear logs
    clearLogsButton.addEventListener("click", () => {
      terminalLogs.replaceChildren();
    });

    // Update guide modal
    let guideLastFocus = null;

    const openGuide = () => {
      if (!guideOverlay) return;
      guideLastFocus = document.activeElement;
      guideOverlay.hidden = false;
      document.body.style.overflow = "hidden";
      if (guideCloseButton) guideCloseButton.focus();
    };

    const closeGuide = () => {
      if (!guideOverlay || guideOverlay.hidden) return;
      guideOverlay.hidden = true;
      document.body.style.overflow = "";
      if (guideLastFocus && typeof guideLastFocus.focus === "function") {
        guideLastFocus.focus();
      }
      guideLastFocus = null;
    };

    if (guideOpenButton) {
      guideOpenButton.addEventListener("click", openGuide);
    }

    if (guideCloseButton) {
      guideCloseButton.addEventListener("click", closeGuide);
    }

    if (guideOverlay) {
      guideOverlay.addEventListener("click", (event) => {
        if (event.target === guideOverlay) closeGuide();
      });
    }

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeGuide();
    });
  }

  /* ---------- Boot ---------- */

  (async function boot() {
    wireStaticEvents();

    const live = await Bridge.init();
    if (live) {
      await refreshPorts();
      try {
        const st = await Bridge.api.get_connection_state();
        setConnectedUI(!!st.connected, st.port);
      } catch (err) {
        appendLog("error", `Could not read connection state: ${err.message}`);
      }
    } else {
      appendLog(
        "warning",
        "Running in SIMULATION mode — no Python backend detected.",
      );
      // A plain browser cannot access real COM ports, so populate a
      // clearly-labelled simulated list (never looks like real hardware).
      const placeholderOption = comPort.querySelector("option[value='']");
      if (placeholderOption) {
        placeholderOption.textContent = "Select COM Port...";
      }
      [
        ["SIM-COM3", "Simulated Serial Port"],
        ["SIM-COM4", "Simulated USB Device"],
      ].forEach(([value, description]) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = `${value} — ${description}`;
        comPort.appendChild(option);
      });
      setConnectedUI(false, null);
    }
  })();
})();
