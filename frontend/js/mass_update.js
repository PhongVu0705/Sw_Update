/* ============================================================
   Software Update Tool — Mass Update screen (mass_update.js)

   Production-line flow:
     connect the selected COM port, then press START. The backend polls
     Target every 0.5 s, flashes and verifies an acknowledged target, waits
     for its 0x82/0x83 unplug response, and repeats for the next PCBA.

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
  const connectButton = $("connect-button");
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
  const lastUpdateCard = $("last-update-card");
  const lastUpdateIcon = $("last-update-icon");
  const lastUpdateStatus = $("last-update-status");
  const lastUpdateDetail = $("last-update-detail");
  const totalSubEl = lastUpdateDetail;

  // Next-step guidance card
  const nextStepCard = $("next-step-card");
  const nextStepIcon = $("next-step-icon");
  const nextStepTitle = $("next-step-title");
  const nextStepText = $("next-step-text");

  // No result dialog is rendered on this screen.
  const resultOverlay = null;
  const resultBadge = null;
  const resultDetected = null;
  const resultExpected = null;
  const resultTotal = null;
  const resultReason = null;
  const resultOkButton = null;
  const resultCloseButton = null;

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
    waiting_for_target: [
      "Waiting for target",
      "Sending Target every 0.5 s until header 0x80...",
    ],
    waiting_for_unplug: [
      "Waiting for unplug",
      "Sending Target every 1.0 s; need 5 consecutive 0x82/0x83 responses...",
    ],
    waiting_for_next_target: [
      "Waiting for next target",
      "Insert the next PCBA; polling Target every 0.5 s...",
    ],
    targeting: [
      "Waiting for target",
      "Sending Target every 0.3 s until header 0x80...",
    ],
    programming: ["Programming MCU", ""],
    verifying: ["Verifying firmware", "Reading FW version and comparing..."],
    done: ["Finished", ""],
  };

  // Operator guidance shown in the next-step card for each run stage.
  const NEXT_STEP_BY_STAGE = {
    waiting_for_target: [
      "running",
      "Insert a PCBA",
      "Place a PCBA into the fixture — polling Target every 0.5 s.",
    ],
    targeting: [
      "running",
      "Insert the first PCBA",
      "Place a PCBA into the fixture to begin the batch.",
    ],
    programming: [
      "running",
      "Flashing in progress",
      "Writing firmware — do not remove the PCBA until verification.",
    ],
    verifying: [
      "running",
      "Verifying firmware",
      "Reading the FW version — keep the PCBA seated.",
    ],
    waiting_for_unplug: [
      "warning",
      "Remove the PCBA",
      "Flash complete — unplug the PCBA so the next cycle can start.",
    ],
    waiting_for_next_target: [
      "success",
      "Insert the next PCBA",
      "PCBA finished — place the next one to continue the batch.",
    ],
    done: [
      "success",
      "Batch finished",
      "Mass update ended — check the pass/fail results above.",
    ],
  };

  const state = {
    connected: false,
    file: null, // { path, name, size, ext } | browser File wrapper
    toolType: "M12",
    running: false,
    // UI lock state (password protected — see "UI Lock / Unlock" section)
    isMassPageLocked: false,
    lockPassword: null,
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

    // Mirror the stage in the next-step guidance card.
    const step = NEXT_STEP_BY_STAGE[stage];
    if (step) setNextStep(step[0], step[1], step[2]);
  }

  function setConnectedUI(connected, port) {
    state.connected = connected;
    statusIndicator.classList.toggle("offline", !connected);
    statusText.textContent = connected
      ? port
        ? `Connected: ${port}`
        : "System Connected"
      : "Not Connected";
    connectButton.classList.toggle("is-connected", connected);
    connectButton.textContent = connected ? "Disconnect" : "Connect";
    refreshNextStep();
  }

  function setFileInfo(file) {
    state.file = file;
    filePathLabel.textContent = file.name;
    fileMeta.textContent = `Size: ${formatFileSize(
      file.size || 0,
    )} · ${(file.ext || "").toUpperCase() || "FILE"}`;
    refreshNextStep();
  }

  /* ---------- Cumulative session counters ---------- */

  function completedCount() {
    return state.passed + state.failed;
  }

  function refreshStatCards(res) {
    const total = completedCount();
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

    if (res) {
      const passed = !!res.pass;
      lastUpdateCard.classList.toggle("pass", passed);
      lastUpdateCard.classList.toggle("fail", !passed);
      lastUpdateIcon.className = `stat-icon ${passed ? "pass" : "fail"}`;
      lastUpdateIcon.innerHTML = `<i class="bi bi-${passed ? "check-lg" : "x-lg"}"></i>`;
      lastUpdateStatus.textContent = passed ? "PASS" : "FAIL";
      lastUpdateStatus.className = `stat-value ${passed ? "pass" : "fail"}`;
    }

    // Last-result detail under the status card
    if (res) {
      const verdict = res.pass ? "PASS" : "FAIL";
      const detected = res.detected ?? "not readable";
      totalSubEl.textContent = `Last: ${verdict} · FW ${detected}`;
    }
  }

  /* ---------- Next-step guidance card ---------- */

  const NEXT_STEP_ICONS = {
    info: "bi-info-circle-fill",
    success: "bi-check-circle-fill",
    warning: "bi-exclamation-triangle-fill",
    danger: "bi-x-octagon-fill",
    running: "bi-arrow-repeat",
  };

  function setNextStep(variant, title, text) {
    if (!nextStepCard) return;
    nextStepCard.className = `panel next-step-card ${variant}`;
    nextStepIcon.innerHTML = `<i class="bi ${
      NEXT_STEP_ICONS[variant] || NEXT_STEP_ICONS.info
    }"></i>`;
    nextStepTitle.textContent = title;
    nextStepText.textContent = text;
  }

  // Chooses the guidance message from whatever the operator still has to do
  // before a run can start (used whenever the run is idle).
  function refreshNextStep() {
    if (state.running) return; // stage events drive the card during a run

    if (!state.connected) {
      setNextStep(
        "info",
        "Step 1 — Connect",
        "Select the COM port in the list, then press Connect.",
      );
      return;
    }
    if (!state.file) {
      setNextStep(
        "info",
        "Step 2 — Select firmware",
        "Browse for the .bin or .csv firmware file to flash.",
      );
      return;
    }
    if (Bridge.available && !state.file.path) {
      setNextStep(
        "warning",
        "Firmware path missing",
        "Drag & drop can't provide a file path in the desktop app — use the Browse button.",
      );
      return;
    }
    if (!expectedFw.value.trim()) {
      setNextStep(
        "warning",
        "Step 3 — Fw version check",
        "Enter the expected firmware version (required), e.g. 1.4.2.",
      );
      return;
    }
    setNextStep(
      "success",
      "Ready to start",
      "Insert the first PCBA into the adapter and press start.",
    );
  }

  /* ============================================================
     UI Lock / Unlock (password protected)
     Clicking the "Mass Update" header title toggles the lock:
       unlocked -> "Set Lock Password" modal, then lock the page
       locked   -> "Enter Password to Unlock" modal
     While locked every interactive control is disabled EXCEPT the
     Start and Stop buttons.
     ============================================================ */

  const lockToggle = $("lock-toggle");
  const lockIcon = $("lock-icon");
  const setLockModal = $("set-lock-modal");
  const setLockForm = $("set-lock-form");
  const setLockPassword = $("set-lock-password");
  const setLockConfirm = $("set-lock-confirm");
  const setLockError = $("set-lock-error");
  const unlockModal = $("unlock-modal");
  const unlockForm = $("unlock-form");
  const unlockPassword = $("unlock-password");
  const unlockError = $("unlock-error");

  // Form controls that receive the `disabled` attribute while locked.
  // Start/Stop buttons are intentionally NOT in this list.
  const lockableControls = [
    comPort,
    refreshPortsButton,
    connectButton,
    expectedFw,
    fileInput,
    clearLogsButton,
    ...toolButtons,
  ];

  // Interactive elements that cannot take `disabled` (browse label,
  // back-button anchor, drop zone): dimmed + click-through via CSS.
  const lockableZones = [dropZone, browseLabel, backButton];

  let activeLockModal = null;
  let lastFocusBeforeLockModal = null;

  function showLockError(errorEl, message) {
    errorEl.textContent = message;
    errorEl.hidden = false;
  }

  function clearLockError(errorEl) {
    errorEl.textContent = "";
    errorEl.hidden = true;
  }

  function openLockModal(modal, firstField) {
    lastFocusBeforeLockModal = document.activeElement;
    modal.hidden = false;
    document.body.style.overflow = "hidden";
    activeLockModal = modal;
    firstField.focus();
  }

  function closeLockModal(modal) {
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    if (activeLockModal === modal) activeLockModal = null;
    document.body.style.overflow = "";
    clearLockError(setLockError);
    clearLockError(unlockError);
    setLockForm.reset();
    unlockForm.reset();
    if (
      lastFocusBeforeLockModal &&
      typeof lastFocusBeforeLockModal.focus === "function"
    ) {
      lastFocusBeforeLockModal.focus();
    }
    lastFocusBeforeLockModal = null;
  }

  // Header icon: open padlock when unlocked, warning padlock when locked.
  function updateLockToggleUI() {
    const locked = state.isMassPageLocked;
    lockToggle.setAttribute("aria-pressed", String(locked));
    lockToggle.title = locked
      ? "Page locked — click to unlock (password required)"
      : "Click to lock the page controls with a password";
    lockToggle.classList.toggle("is-locked", locked);
    lockIcon.className = locked
      ? "bi bi-lock-fill text-warning lock-icon"
      : "bi bi-unlock lock-icon";
  }

  // Applies / releases the lock restrictions on every control except
  // Start and Stop. Safe to call at any time — while a run is active the
  // run-control functions own those controls, so unlocking mid-run does
  // not re-enable them (endRunUI() calls this again when the run ends).
  function applyLockState() {
    const locked = state.isMassPageLocked;

    lockableControls.forEach((el) => {
      if (!el) return;
      if (locked) {
        el.disabled = true;
      } else if (!state.running) {
        el.disabled = false;
      }
    });

    lockableZones.forEach((el) => {
      if (!el) return;
      el.classList.toggle("ui-locked", locked);
    });

    // The back button is a plain anchor: take it out of the tab order
    // while locked (its click handler blocks activation as well).
    if (locked) {
      backButton.setAttribute("tabindex", "-1");
      backButton.setAttribute("aria-disabled", "true");
    } else {
      backButton.removeAttribute("tabindex");
      backButton.removeAttribute("aria-disabled");
    }

    document.body.classList.toggle("mass-page-locked", locked);
    updateLockToggleUI();
  }

  // Central lock state change: apply restrictions + inform the operator.
  function setLocked(locked) {
    state.isMassPageLocked = locked;
    applyLockState();
    appendLog(
      "info",
      locked
        ? "Page locked — controls are disabled (Start/Stop stay active). Click the 'Mass Update' title and enter the password to unlock."
        : "Page unlocked — all controls restored.",
    );
  }

  // First click on the title (page unlocked): ask for a lock password,
  // then lock the page once it is entered and confirmed.
  function requestLock() {
    openLockModal(setLockModal, setLockPassword);
  }

  // Click on the title while locked: ask for the password to unlock.
  function requestUnlock() {
    openLockModal(unlockModal, unlockPassword);
  }

  function onLockToggleActivated() {
    if (activeLockModal) return; // a lock dialog is already open
    if (state.isMassPageLocked) {
      requestUnlock();
    } else {
      requestLock();
    }
  }

  /* ---------- Run control UI ---------- */

  function beginRun() {
    state.running = true;
    startButton.disabled = true;
    stopButton.disabled = false;
    comPort.disabled = true;
    refreshPortsButton.disabled = true;
    connectButton.disabled = true;
    expectedFw.disabled = true;
    setProgress(0);
    setNextStep(
      "running",
      "Starting mass update",
      "Preparing the fixture — the first stage will begin shortly.",
    );
  }

  function endRunUI() {
    state.running = false;
    startButton.disabled = false;
    stopButton.disabled = true;
    comPort.disabled = false;
    refreshPortsButton.disabled = false;
    connectButton.disabled = false;
    expectedFw.disabled = false;
    // Re-apply the UI lock so run-driven re-enabling never overrides it.
    applyLockState();
    refreshNextStep();
  }

  function validateInputs() {
    if (!comPort.value) {
      appendLog("warning", "Cannot start: no COM port selected.");
      setNextStep(
        "warning",
        "Step 1 — Select COM port",
        "Choose a COM port from the dropdown before starting.",
      );
      comPort.focus();
      return false;
    }
    if (!state.connected) {
      appendLog(
        "warning",
        "Cannot start: connect to the selected COM port first.",
      );
      setNextStep(
        "warning",
        "Step 1 — Connect",
        "Press Connect to open the selected COM port first.",
      );
      connectButton.focus();
      return false;
    }
    if (!state.file || (Bridge.available && !state.file.path)) {
      appendLog("warning", "Cannot start: select a firmware file first.");
      setNextStep(
        "warning",
        "Step 2 — Select firmware",
        Bridge.available && state.file && !state.file.path
          ? "Use the Browse button — drag & drop has no file path in the desktop app."
          : "Choose the .bin or .csv firmware file to flash.",
      );
      dropZone.scrollIntoView({ behavior: "smooth", block: "nearest" });
      return false;
    }
    const ext = (state.file.ext || "").toLowerCase();
    if (ext !== "bin" && ext !== "csv") {
      appendLog("error", "Unsupported file type - choose a .bin or .csv file.");
      setNextStep(
        "danger",
        "Unsupported file type",
        "Select a .bin or .csv firmware file instead.",
      );
      return false;
    }
    // FW version check input is REQUIRED for mass update.
    const fw = expectedFw.value.trim();
    if (!fw) {
      appendLog(
        "warning",
        "Fw version check is REQUIRED - enter the expected firmware version to run.",
      );
      setNextStep(
        "warning",
        "Step 3 — Fw version check",
        "Enter the expected firmware version (required), e.g. 1.4.2.",
      );
      expectedFw.focus();
      return false;
    }
    if (!VERSION_RE.test(fw)) {
      appendLog(
        "error",
        "Invalid FW version format - use decimal numbers separated by dots, e.g. 1.4.2",
      );
      setNextStep(
        "danger",
        "Invalid FW version",
        "Use decimal numbers separated by dots, e.g. 1.4.2.",
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
    resultReason.textContent = ok
      ? "FW read matches expected version"
      : res.reason || "Unknown failure";

    lastFocusBeforeModal = document.activeElement;
    resultOverlay.hidden = false;
    document.body.style.overflow = "hidden";
    if (resultOkButton) resultOkButton.focus();
  }

  function hideResultModal() {
    if (!resultOverlay || resultOverlay.hidden) return;
    resultOverlay.hidden = true;
    document.body.style.overflow = "";
    if (
      lastFocusBeforeModal &&
      typeof lastFocusBeforeModal.focus === "function"
    ) {
      lastFocusBeforeModal.focus();
    }
    lastFocusBeforeModal = null;
  }

  /* ---------- Finish handling ---------- */

  function recordMassResult(res) {
    if (res.pass) {
      state.passed += 1;
      setProgress(100);
      appendLog(
        "success",
        `=== MASS UPDATE FINISHED: PASS === FW ${res.detected ?? "?"}`,
      );
    } else {
      state.failed += 1;
      appendLog(
        "error",
        `=== MASS UPDATE FINISHED: FAIL - ${res.reason || "unknown"} ===`,
      );
    }

    refreshStatCards(res);
  }

  function handleMassFinished(res) {
    endRunUI();
    if (res && res.reason && !res.stopped) {
      appendLog("error", `Continuous update ended: ${res.reason}`);
    }

    // Reflect how the run ended in the guidance card.
    if (res && res.stopped) {
      setNextStep(
        "warning",
        "Update stopped",
        "Mass update was stopped — press Start to run another batch.",
      );
    } else if (res && res.reason) {
      setNextStep(
        "danger",
        "Update ended with an error",
        `${res.reason} — resolve the issue, then press Start to retry.`,
      );
    } else {
      setNextStep(
        "success",
        "Batch finished",
        "All PCBAs done — press Start to run another batch.",
      );
    }
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
          appendLog("error", (r && r.message) || "Failed to start mass update");
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
      stage: "targeting",
      targetSends: 0,
      progress: 0,
      verified: false,
      unplugSends: 0,
    };
    const expected = expectedFw.value.trim();

    appendLog(
      "info",
      `[SIM] Starting simulated mass update of ${state.file.name} (${state.toolType}) on ${portName}...`,
    );
    setStage("targeting");

    const tick = () => {
      if (!state.running) return;

      if (sim.stage === "targeting") {
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
        recordMassResult({
          pass: !mismatch,
          detected: detected || null,
          expected,
          reason: mismatch ? "FW version mismatch" : "",
        });
        sim.stage = "waiting_for_unplug";
        sim.unplugSends = 0;
        setStage("waiting_for_unplug");
      } else if (sim.stage === "waiting_for_unplug") {
        sim.unplugSends += 1;
        if (sim.unplugSends >= 5) {
          appendLog("info", "[SIM] RX header 82 - target removed.");
          sim.stage = "targeting";
          sim.targetSends = 0;
          sim.progress = 0;
          sim.verified = false;
          setStage("waiting_for_next_target");
        }
      }

      state.simTimerId = setTimeout(
        tick,
        sim.stage === "waiting_for_unplug" ? 1000 : 500,
      );
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

  Bridge.on("onMassResult", (res) => recordMassResult(res || {}));
  Bridge.on("onMassFinished", (res) => handleMassFinished(res || {}));

  // ---- Static DOM events ----

  function wireStaticEvents() {
    // Explicit connection: the continuous update worker only uses this port.
    connectButton.addEventListener("click", async () => {
      if (state.running) return;
      if (!comPort.value) {
        appendLog("warning", "Cannot connect: no COM port selected.");
        comPort.focus();
        return;
      }
      connectButton.disabled = true;
      try {
        if (Bridge.available) {
          const r = state.connected
            ? await Bridge.api.disconnect_port()
            : await Bridge.api.connect_port(comPort.value);
          if (r.status !== "SUCCESS")
            appendLog("error", r.message || "Connection failed");
        } else {
          setConnectedUI(!state.connected, comPort.value);
          appendLog(
            "info",
            `[SIM] ${state.connected ? "Connected" : "Disconnected"} ${comPort.value}`,
          );
        }
      } catch (err) {
        appendLog("error", `Connection error: ${err.message}`);
      } finally {
        connectButton.disabled = false;
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

    // Expected FW input: keep the guidance card in sync while typing
    expectedFw.addEventListener("input", () => {
      if (!state.running) refreshNextStep();
    });

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
        handleMassFinished({ stopped: true, reason: "Stopped by operator" });
      }
    });

    // Clear logs
    clearLogsButton.addEventListener("click", () => {
      terminalLogs.replaceChildren();
    });

    // Back button ("Main Menu"): abort and disconnect before leaving.
    backButton.addEventListener("click", async (event) => {
      if (state.isMassPageLocked) {
        // Page is locked: navigation stays blocked until it is unlocked.
        event.preventDefault();
        return;
      }
      if (!state.running && !state.connected) return;

      event.preventDefault();
      backButton.style.pointerEvents = "none"; // guard against double clicks
      try {
        if (Bridge.available) {
          if (state.running) {
            appendLog(
              "warning",
              "Mass update aborted - returning to Main Menu...",
            );
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

    // ---- UI lock / unlock ----

    // The header title acts as the lock toggle (mouse + keyboard).
    lockToggle.addEventListener("click", onLockToggleActivated);
    lockToggle.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onLockToggleActivated();
      }
    });

    // "Set Lock Password" modal: validate, remember, then lock the page.
    setLockForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const password = setLockPassword.value;
      const confirm = setLockConfirm.value;

      if (!password) {
        showLockError(setLockError, "Please enter a password.");
        setLockPassword.focus();
        return;
      }
      if (password !== confirm) {
        showLockError(setLockError, "Passwords do not match — try again.");
        setLockConfirm.focus();
        return;
      }

      state.lockPassword = password;
      closeLockModal(setLockModal);
      setLocked(true);
    });

    // "Enter Password to Unlock" modal: verify, then unlock or show the
    // inline error.
    unlockForm.addEventListener("submit", (event) => {
      event.preventDefault();
      if (unlockPassword.value === state.lockPassword) {
        closeLockModal(unlockModal);
        setLocked(false);
      } else {
        showLockError(unlockError, "Incorrect password");
        unlockPassword.select();
      }
    });

    // Close lock dialogs via the X / Cancel buttons and the backdrop.
    [setLockModal, unlockModal].forEach((modal) => {
      modal.addEventListener("click", (event) => {
        if (event.target === modal) closeLockModal(modal);
      });
      modal.querySelectorAll("[data-close-lock-modal]").forEach((button) =>
        button.addEventListener("click", () => closeLockModal(modal)),
      );
    });

    // Escape closes whichever lock dialog is open.
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && activeLockModal) {
        closeLockModal(activeLockModal);
      }
    });

    // Basic focus trap inside the open lock dialog.
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Tab" || !activeLockModal) return;
      const dialog = activeLockModal.querySelector(".modal");
      const focusable = dialog.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
  }

  /* ---------- Boot ---------- */

  (async function boot() {
    wireStaticEvents();

    // The lock is intentionally per-visit (in-memory only): leaving the
    // page via Main Menu — or reloading — always starts unlocked again.
    applyLockState(); // normalise the header icon / tooltip to that state

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

    refreshNextStep();
  })();
})();
