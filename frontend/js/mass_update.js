/* ============================================================
   Software Update Tool — Mass Update screen (mass_update.js)

   Production-line flow:
     press START -> the backend auto-connects the selected COM
     port every 0.5 s, then sends the Target select command
     (M12/M18) every 0.5 s until the response header byte is
     0x80, flashes the firmware exactly like the Update page,
     reads back the FW version and compares it with the
     REQUIRED user input, disconnects the port and pops up a
     result modal asking the operator to insert the next PCBA.

   Real mode  : talks to the Python backend through pywebview
                (window.pywebview.api) + pushed events.
   Simulation : falls back to a local demo when opened in a
                plain browser without the backend.
   ============================================================ */

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  /* ---------- Element references ---------- */

  const form = $("mass-form");
  const fileInput = $("firmware-file");
  const filePathLabel = $("firmware-file-label");
  const fileMeta = $("firmware-file-meta");
  const dropZone = $("drop-zone");
  const browseLabel = dropZone.querySelector(".browse-button");
  const refreshPortsButton = $("refresh-ports-button");
  const backButton = $("back-button");
  const comPort = $("com-port");
  const toolButtons = Array.from(document.querySelectorAll(".tool-btn"));
  const expectedFw = $("expected-fw");
  const startButton = $("start-button");
  const stopButton = $("stop-button");
  const clearLogsButton = $("clear-logs");
  const terminalLogs = $("terminal-logs");

  // New stat cards (cumulative session counters)
  const rateValueEl = $("rate-value");
  const rateDetailEl = $("rate-detail");
  const totalCountEl = $("total-count");
  const totalSubEl = $("total-sub");

  // Result modal
  const resultOverlay = $("result-overlay");
  const resultBadge = $("result-badge");
  const resultDetected = $("result-detected");
  const resultExpected = $("result-expected");
  const resultTotal = $("result-total");
  const resultReason = $("result-reason");
  const resultOkButton = $("result-ok-button");
  const resultCloseButton = resultOverlay
    ? resultOverlay.querySelector("[data-close-result]")
    : null;

  const progressBarFill = $("progress-bar-fill");
  const progressPercentage = $("progress-percentage");
  const progressTrack = $("progress-track");
  const progressLabel = $("progress-label");
  const speedInfo = $("speed-info");
  const statusIndicator = document.querySelector(
    ".screen-header .status-indicator",
  );
  const statusText = statusIndicator.querySelector(".status-text");

  /* ---------- Constants & state ---------- */

  // Version format accepted for the required FW check input.
  const VERSION_RE = /^\d+(\.\d+){0,3}$/;

  const STAGE_LABELS = {
    connecting: [
      "Connecting to device",
      "Auto-connecting every 0.5 s - plug in the PCBA...",
    ],
    targeting: [
      "Waiting for target ACK",
      "Sending Target command every 0.5 s until header byte 0x80...",
    ],
    programming: ["Programming MCU", ""],
    verifying: ["Verifying firmware", "Reading FW version and comparing..."],
    done: ["Finished", ""],
  };

  const state = {
    connected: false,
    file: null, // { path, name, size, ext } | browser File wrapper
    toolType: "M12",
    running: false,
    // Cumulative session counters (persist across PCBAs)
    passed: 0,
    failed: 0,
    // Simulation-only state
    simTimerId: null,
    simProgress: 0,
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

  function logLine(message) {
    appendLog(classifyLevel(message), message);
  }

  function setProgress(value) {
    const clamped = Math.min(100, Math.max(0, value));
    progressBarFill.style.width = `${clamped}%`;
    progressPercentage.textContent = `${Math.round(clamped)}%`;
    progressTrack.setAttribute("aria-valuenow", String(Math.round(clamped)));
  }

  function setStage(stage) {
    const [label, hint] = STAGE_LABELS[stage] || ["Working", ""];
    progressLabel.textContent = label;
    speedInfo.textContent = hint;
  }

  function setConnectedUI(connected, port) {
    state.connected = connected;
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

  /* ---------- Cumulative session counters ---------- */

  function completedCount() {
    return state.passed + state.failed;
  }

  function refreshStatCards(res) {
    const total = completedCount();
    totalCountEl.textContent = String(total);

    if (total === 0) {
      rateValueEl.textContent = "—";
      rateValueEl.className = "stat-value";
      rateDetailEl.textContent = "Passed 0 · Failed 0";
    } else {
      const passPct = Math.round((state.passed / total) * 1000) / 10;
      const failPct = Math.round((state.failed / total) * 1000) / 10;
      const allPass = state.failed === 0;
      rateValueEl.className = `stat-value ${allPass ? "pass" : passPct >= 50 ? "pass" : "fail"}`;
      rateValueEl.textContent = `${passPct}% / ${failPct}%`;
      rateDetailEl.textContent = `Passed ${state.passed} · Failed ${state.failed}`;
    }

    // Last-result line under the TOTAL card
    if (res) {
      const verdict = res.pass ? "PASS" : "FAIL";
      const detected = res.detected ?? "not readable";
      totalSubEl.textContent = `Last: ${verdict} · FW ${detected}`;
    }
  }

  /* ---------- Run control UI ---------- */

  function beginRun() {
    state.running = true;
    startButton.disabled = true;
    stopButton.disabled = false;
    comPort.disabled = true;
    refreshPortsButton.disabled = true;
    expectedFw.disabled = true;
    setProgress(0);
    hideResultModal();
  }

  function endRunUI() {
    state.running = false;
    startButton.disabled = false;
    stopButton.disabled = true;
    comPort.disabled = false;
    refreshPortsButton.disabled = false;
    expectedFw.disabled = false;
    setConnectedUI(false, null);
  }

  function validateInputs() {
    if (!comPort.value) {
      appendLog("warning", "Cannot start: no COM port selected.");
      comPort.focus();
      return false;
    }
    if (!state.file || (Bridge.available && !state.file.path)) {
      appendLog("warning", "Cannot start: select a firmware file first.");
      dropZone.scrollIntoView({ behavior: "smooth", block: "nearest" });
      return false;
    }
    const ext = (state.file.ext || "").toLowerCase();
    if (ext !== "bin" && ext !== "csv") {
      appendLog("error", "Unsupported file type - choose a .bin or .csv file.");
      return false;
    }
    // FW version check input is REQUIRED for mass update.
    const fw = expectedFw.value.trim();
    if (!fw) {
      appendLog(
        "warning",
        "Fw version check is REQUIRED - enter the expected firmware version to run.",
      );
      expectedFw.focus();
      return false;
    }
    if (!VERSION_RE.test(fw)) {
      appendLog(
        "error",
        "Invalid FW version format - use decimal numbers separated by dots, e.g. 1.4.2",
      );
      expectedFw.select();
      return false;
    }
    return true;
  }

    /* ---------- Result modal ---------- */

  let lastFocusBeforeModal = null;

  function showResultModal(res) {
    if (!resultOverlay) return;
    const ok = !!res.pass;

    resultBadge.textContent = ok ? "PASS" : "FAIL";
    resultBadge.className = `result-badge ${ok ? "pass" : "fail"}`;
    resultDetected.textContent = res.detected ?? "Not readable";
    resultExpected.textContent = res.expected ?? "—";
    resultTotal.textContent = String(completedCount());
    resultReason.textContent = ok ? "FW read matches expected version" : res.reason || "Unknown failure";

    lastFocusBeforeModal = document.activeElement;
    resultOverlay.hidden = false;
    document.body.style.overflow = "hidden";
    if (resultOkButton) resultOkButton.focus();
  }

  function hideResultModal() {
    if (!resultOverlay || resultOverlay.hidden) return;
    resultOverlay.hidden = true;
    document.body.style.overflow = "";
    if (lastFocusBeforeModal && typeof lastFocusBeforeModal.focus === "function") {
      lastFocusBeforeModal.focus();
    }
    lastFocusBeforeModal = null;
  }

  /* ---------- Finish handling ---------- */

  function handleMassFinished(res) {
    endRunUI();

    if (res.pass) {
      state.passed += 1;
      setProgress(100);
      appendLog("success", `=== MASS UPDATE FINISHED: PASS === FW ${res.detected ?? "?"}`);
    } else {
      state.failed += 1;
      appendLog("error", `=== MASS UPDATE FINISHED: FAIL - ${res.reason || "unknown"} ===`);
    }

    refreshStatCards(res);
    showResultModal(res);
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
    if (state.running) return;
    if (!validateInputs()) return;

    beginRun();

    if (Bridge.available) {
      try {
        const r = await Bridge.api.run_mass_update(
          comPort.value,
          state.file.path,
          state.toolType,
          expectedFw.value.trim(),
        );
        if (!r || r.status !== "STARTED") {
          appendLog(
            "error",
            (r && r.message) || "Failed to start mass update",
          );
          endRunUI();
          return;
        }
        // Completion arrives asynchronously via onMassFinished.
      } catch (err) {
        appendLog("error", `Mass update failed to start: ${err.message}`);
        endRunUI();
      }
    } else {
      simulateRun(comPort.value || "SIM-COM3");
    }
  }

    /* ============================================================
     Simulation mode (plain browser fallback)
     Reproduces the production flow at the same 0.5 s cadence:
       auto-connect -> target ACK 0x80 -> flashing -> FW verify
     ============================================================ */

  function stopSim() {
    if (state.simTimerId !== null) {
      clearTimeout(state.simTimerId);
      state.simTimerId = null;
    }
  }

  function simulateRun(portName) {
    const sim = {
      stage: "connecting",
      attempt: 0,
      targetSends: 0,
      progress: 0,
      verified: false,
    };
    const expected = expectedFw.value.trim();

    appendLog(
      "info",
      `[SIM] Starting simulated mass update of ${state.file.name} (${state.toolType}) on ${portName}...`,
    );
    setStage("connecting");

    const tick = () => {
      if (!state.running) return;

      if (sim.stage === "connecting") {
        sim.attempt += 1;
        appendLog("info", `[SIM] Auto-connect attempt ${sim.attempt} on ${portName}...`);
        if (sim.attempt >= 3) {
          setConnectedUI(true, portName);
          appendLog("success", `[SIM] Connected to ${portName}.`);
          sim.stage = "targeting";
          setStage("targeting");
        }
      } else if (sim.stage === "targeting") {
        const cmd = state.toolType === "M18" ? "70 01 01 01" : "70 01 01 11";
        sim.targetSends += 1;
        if (sim.targetSends < 3) {
          appendLog(
            "info",
            `[SIM] Sent Target command (${cmd}), response not 80 yet - retrying in 0.5 s...`,
          );
        } else {
          appendLog(
            "process",
            `[SIM] RX header byte 80 - target acknowledged after ${sim.targetSends} attempts.`,
          );
          sim.stage = "programming";
          setStage("programming");
        }
      } else if (sim.stage === "programming") {
        sim.progress = Math.min(100, sim.progress + 4 + Math.random() * 5);
        setProgress(sim.progress);
        speedInfo.textContent =
          sim.progress >= 100
            ? ""
            : `Estimated Time Remaining: ~${Math.round(
                ((100 - sim.progress) / 100) * 60,
              )} seconds`;
        if (Math.random() < 0.35) {
          const block = Math.max(1, Math.round((sim.progress / 100) * 64));
          appendLog(
            "process",
            `[SIM] Flashing firmware block ${block}/64 to the PCBA...`,
          );
        }
        if (sim.progress >= 100) {
          appendLog("success", "[SIM] Flashing sequence completed.");
          sim.stage = "verifying";
          setStage("verifying");
        }
      } else if (sim.stage === "verifying" && !sim.verified) {
        sim.verified = true;
        const mismatch = Math.random() < 0.2;
        let detected = expected;
        if (mismatch && expected) {
          const segments = expected.split(".").map(Number);
          segments[segments.length - 1] += 1;
          detected = `${segments.join(".")}.0`;
        }
        appendLog(
          mismatch ? "error" : "success",
          mismatch
            ? `[SIM] FW read ${detected}, expected ${expected}`
            : `[SIM] FW read matches: ${detected}`,
        );
        handleMassFinished({
          pass: !mismatch,
          detected: detected || null,
          expected,
          reason: mismatch ? "FW version mismatch" : "",
        });
        return;
      }

      state.simTimerId = setTimeout(tick, 500);
    };

    state.simTimerId = setTimeout(tick, 500);
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

  Bridge.on("onConnectionState", (st) =>
    setConnectedUI(!!(st && st.connected), st ? st.port : null),
  );

  Bridge.on("onMassStage", (stage) => setStage(String(stage || "")));

  Bridge.on("onMassFinished", (res) => handleMassFinished(res || {}));

  // ---- Static DOM events ----

  function wireStaticEvents() {
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
        if (!state.running) refreshPortsButton.disabled = false;
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

        // Stop (shared RunController with the backend)
    stopButton.addEventListener("click", async () => {
      if (!state.running) return;

      if (Bridge.available) {
        stopButton.disabled = true;
        try {
          await Bridge.api.stop_update();
          // Final FAIL result arrives via onMassFinished.
        } catch (err) {
          appendLog("error", `Stop failed: ${err.message}`);
          stopButton.disabled = false;
        }
      } else {
        stopSim();
        appendLog("error", "[SIM] Mass update aborted by operator.");
        handleMassFinished({
          pass: false,
          detected: null,
          expected: expectedFw.value.trim() || null,
          reason: "Stopped by operator",
        });
      }
    });

    // Clear logs
    clearLogsButton.addEventListener("click", () => {
      terminalLogs.replaceChildren();
    });

        // Result modal ("Insert next PCBA")
    if (resultOkButton) {
      resultOkButton.addEventListener("click", hideResultModal);
    }
    if (resultCloseButton) {
      resultCloseButton.addEventListener("click", hideResultModal);
    }
    if (resultOverlay) {
      resultOverlay.addEventListener("click", (event) => {
        if (event.target === resultOverlay) hideResultModal();
      });
    }

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") hideResultModal();
    });

        // Back button ("Main Menu"): abort and disconnect before leaving.
    backButton.addEventListener("click", async (event) => {
      if (!state.running && !state.connected) return;

      event.preventDefault();
      backButton.style.pointerEvents = "none"; // guard against double clicks
      try {
        if (Bridge.available) {
          if (state.running) {
            appendLog("warning", "Mass update aborted - returning to Main Menu...");
            await Bridge.api.stop_update();
          }
          await Bridge.api.disconnect_port();
        } else {
          stopSim();
        }
      } catch (err) {
        appendLog("error", `Disconnect failed: ${err.message}`);
      } finally {
        window.location.href = backButton.href;
      }
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
        "Running in SIMULATION mode - no Python backend detected.",
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
