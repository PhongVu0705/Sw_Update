/* ============================================================
   Software Update Tool — Manual Command Send screen (manual.js)
   Real mode  : talks to the Python backend through pywebview
                (window.pywebview.api) + pushed events.
   Simulation : falls back to a local demo when opened in a
                plain browser without the backend.
   ============================================================ */

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  /* ---------- Element references ---------- */

  const form = $("command-form");
  const comPort = $("com-port");
  const connectButton = $("connect-button");
  const refreshPortsButton = $("refresh-ports-button");
  const backButton = $("back-button");
  const commandInput = $("command-input");
  const clearLogsButton = $("clear-logs");
  const terminalLogs = $("terminal-logs");
  const quickButtons = document.querySelectorAll(".quick-btn[data-command]");

  const overlay = $("modal-overlay");
  const modalTitle = $("modal-title");
  const modalBody = $("modal-body");
  const modalClose = overlay
    ? overlay.querySelector("[data-close-modal]")
    : null;
  const modalCopy = overlay ? overlay.querySelector("[data-copy-modal]") : null;

  const statusIndicator = document.querySelector(
    ".screen-header .status-indicator",
  );
  const statusText = statusIndicator.querySelector(".status-text");

  /* ---------- State ---------- */

  let isConnected = false;

  /* Text of the current modal result, used by the Copy button */
  let modalCopyText = "";

  /* ---------- Simulated device responses (simulation mode only) ---------- */

  const RESPONSES = {
    "READ FW VERSION": "FW v1.4.2 (build 20260812)",
    "READ FW P/N": "P/N 49-32-0100 rev B",
    "READ MPBID": "MPBID 0x4D5042494407A3",
    "GET CALIBRATION": "CAL torque=8.2Nm offset=0x1F crc=OK",
    "AUTH DEFAULT_METCO": "AUTH OK — session opened",
    "TARGET M18": "Target set: M18",
    "TARGET M12": "Target set: M12",
    "WIPE COUNTERS": "Counters and histograms wiped",
  };

  // Commands whose response carries no data - log only, no popup
  const NO_POPUP_COMMANDS = new Set(["WIPE COUNTERS"]);

  const QUICK_RESULTS = {
    "READ FW VERSION": [
      ["Firmware version", "v1.4.2"],
      ["Build date", "2026-08-12"],
      ["CRC check", "PASS"],
    ],
    "READ FW P/N": [
      ["Part number", "49-32-0100"],
      ["Revision", "B"],
    ],
    "READ MPBID": [
      ["MPBID", "0x4D5042494407A3"],
      ["Encoding", "HEX / 12 bytes"],
    ],
    "GET CALIBRATION": [
      ["Torque calibration", "8.2 Nm"],
      ["Offset register", "0x1F"],
      ["CRC check", "PASS"],
    ],
    "AUTH DEFAULT_METCO": [
      ["Authentication", "OK"],
      ["Session", "Opened"],
      ["Access level", "Service"],
    ],
    "TARGET M18": [
      ["Target device", "M18 FUEL Impact Wrench"],
      ["Selection status", "Active"],
    ],
    "TARGET M12": [
      ["Target device", "M12 Impact Driver"],
      ["Selection status", "Active"],
    ],
  };

  /* Map quick-command labels to backend API keys */
  const COMMAND_MAP = {
    "TARGET M18": "target_m18",
    "TARGET M12": "target_m12",
    "AUTH DEFAULT_METCO": "metco_password",
    "GET CALIBRATION": "calibration",
    "READ FW VERSION": "fw_version",
    "READ FW P/N": "fw_pn",
    "READ MPBID": "mpbid",
    "WIPE COUNTERS": "wipe_counters",
  };

  /* ---------- Helpers ---------- */

  const timestamp = () => {
    const now = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    return `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(
      now.getSeconds(),
    )}`;
  };

  const escapeHtml = (text) => {
    const scratch = document.createElement("div");
    scratch.textContent = String(text);
    return scratch.innerHTML;
  };

  function classifyLevel(message) {
    if (/SUCCESS|PASS\b|verified/i.test(message)) return "success";
    if (/ERROR|FAIL\b|Traceback|aborted|mismatch/i.test(message))
      return "error";
    if (/WARNING|WARN\b|TIMEOUT|no response/i.test(message)) return "warning";
    return "info";
  }

  function appendLog(level, message) {
    const line = document.createElement("p");
    line.className = `log-line log-${level}`;
    line.textContent = `[${timestamp()}] ${message}`;
    terminalLogs.appendChild(line);
    terminalLogs.scrollTop = terminalLogs.scrollHeight;
  }

  function setConnectedUI(connected, port) {
    isConnected = connected;
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

  /* ---------- Result modal ---------- */

  function openResultModal(title, command, rows) {
    const rowsHtml = rows
      .map(
        ([key, value]) =>
          `<div class="result-row"><span class="result-key">${escapeHtml(
            key,
          )}</span><span class="result-value">${escapeHtml(
            value,
          )}</span></div>`,
      )
      .join("");

    modalTitle.textContent = title || "Command Result";
    modalBody.innerHTML = `<p class="result-command">Command: <code>${escapeHtml(
      command,
    )}</code></p>${rowsHtml}`;

    // Copy the raw result - drop the "Data:" label prefix
    modalCopyText = rows
      .map(([, value]) => String(value))
      .map((text) => text.replace(/^Data:\s*/, ""))
      .join(String.fromCharCode(10));
    resetCopyButton();

    overlay.hidden = false;
    document.body.style.overflow = "hidden";
    modalClose.focus();
  }

  function closeModal() {
    if (!overlay || overlay.hidden) {
      return;
    }
    overlay.hidden = true;
    document.body.style.overflow = "";
  }

  function resetCopyButton() {
    if (!modalCopy) {
      return;
    }
    modalCopy.classList.remove("copied");
    const label = modalCopy.querySelector("span");
    if (label) {
      label.textContent = "Copy";
    }
  }

  async function copyModalResult() {
    if (!modalCopyText) {
      return;
    }

    let copied = false;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      try {
        await navigator.clipboard.writeText(modalCopyText);
        copied = true;
      } catch (err) {
        copied = false;
      }
    }
    if (!copied) {
      // Fallback for contexts without the async clipboard API
      const scratch = document.createElement("textarea");
      scratch.value = modalCopyText;
      scratch.setAttribute("readonly", "");
      scratch.style.position = "fixed";
      scratch.style.opacity = "0";
      document.body.appendChild(scratch);
      scratch.select();
      try {
        copied = document.execCommand("copy");
      } catch (copyErr) {
        copied = false;
      }
      document.body.removeChild(scratch);
    }

    if (!copied) {
      appendLog("error", "Unable to copy result to clipboard.");
      return;
    }

    if (modalCopy) {
      modalCopy.classList.add("copied");
      const label = modalCopy.querySelector("span");
      if (label) {
        label.textContent = "Copied!";
      }
      setTimeout(resetCopyButton, 1200);
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

  async function onQuickCommand(button) {
    const label = button.getAttribute("data-command");
    const key = COMMAND_MAP[label];

    if (!isConnected) {
      appendLog("warning", "Cannot send: no device connected.");
      comPort.focus();
      return;
    }
    if (!key) {
      appendLog("warning", `No backend mapping for quick command: ${label}`);
      return;
    }

    button.disabled = true;
    try {
      const r = await Bridge.api.run_quick_command(key);
      if (r.status === "NO_DATA") {
        // Response carried no data (e.g. plain ACK) - log only, no popup
        appendLog("info", `${r.title}: ${r.result}`);
      } else if (r.status === "SUCCESS") {
        openResultModal(r.title, label, [["Result", r.result]]);
      } else {
        openResultModal(r.title || "Command Result", label, [
          ["Status", r.status],
          ["Result", r.result || r.message || "Unknown error"],
        ]);
      }
    } catch (err) {
      appendLog("error", `Quick command failed: ${err.message}`);
    } finally {
      button.disabled = false;
    }
  }

  async function onSend(hexCommand) {
    if (!isConnected) {
      appendLog("warning", "Cannot send: no device connected.");
      comPort.focus();
      return;
    }

    sendButtonLock(true);
    try {
      const r = await Bridge.api.run_hex_command(hexCommand);
      if (r.status !== "SUCCESS") {
        appendLog("error", r.message || "Command failed");
      }
    } catch (err) {
      appendLog("error", `Send failed: ${err.message}`);
    } finally {
      sendButtonLock(false);
    }
  }

  function sendButtonLock(disabled) {
    const sendButton = $("send-button");
    if (sendButton) {
      sendButton.disabled = disabled;
    }
  }

  /* ============================================================
     Simulation mode (plain browser fallback)
     ============================================================ */

  function simulateQuickCommand(label) {
    if (!isConnected) {
      appendLog("warning", "Cannot send: no device connected.");
      comPort.focus();
      return;
    }

    // Reading calibration data sends the METCO password first
    // (mirrors the backend run_quick_command behaviour).
    if (label === "GET CALIBRATION") {
      appendLog("sent", "[SIM] >> AUTH DEFAULT_METCO");
      setTimeout(
        () => appendLog("response", "[SIM] << AUTH OK — session opened"),
        250,
      );
    }

    appendLog("sent", `[SIM] >> ${label}`);
    const response =
      Object.prototype.hasOwnProperty.call(RESPONSES, label) === true
        ? RESPONSES[label]
        : "OK";
    setTimeout(() => appendLog("response", `[SIM] << ${response}`), 250);

    if (NO_POPUP_COMMANDS.has(label)) {
      return; // no data in response - no popup
    }

    const rows =
      Object.prototype.hasOwnProperty.call(QUICK_RESULTS, label) === true
        ? QUICK_RESULTS[label]
        : [["Result", response]];

    setTimeout(() => openResultModal("Command Result", label, rows), 300);
  }

  function simulateSend(hexCommand) {
    if (!isConnected) {
      appendLog("warning", "Cannot send: no device connected.");
      comPort.focus();
      return;
    }
    if (!hexCommand) {
      appendLog("warning", "Cannot send: command is empty.");
      commandInput.focus();
      return;
    }

    appendLog("sent", `[SIM] >> ${hexCommand}`);
    setTimeout(() => appendLog("response", "[SIM] << OK"), 250);
  }

  /* ============================================================
     Event wiring & boot
     ============================================================ */

  // Events pushed from Python (registered up-front)
  Bridge.on("onLogFromPy", (message) => {
    const msg = String(message);
    appendLog(classifyLevel(msg), msg);
  });

  Bridge.on("onConnectionState", (st) =>
    setConnectedUI(!!(st && st.connected), st ? st.port : null),
  );

  // Connection button
  connectButton.addEventListener("click", async () => {
    if (Bridge.available) {
      connectButton.disabled = true;
      try {
        if (!isConnected) {
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
      if (!isConnected && !comPort.value) {
        appendLog("warning", "Cannot connect: no COM port selected.");
        comPort.focus();
        return;
      }
      const port = comPort.value || "COM3 (simulated)";
      setConnectedUI(!isConnected, port);
      appendLog(
        isConnected ? "success" : "info",
        isConnected
          ? `[SIM] Connected to device on ${port}`
          : "[SIM] Disconnected from device",
      );
    }
  });

  // Back button ("Main Menu"): disconnect the COM port before leaving.
  // When not connected the link behaves normally.
  backButton.addEventListener("click", async (event) => {
    if (!isConnected) return;

    event.preventDefault();
    backButton.style.pointerEvents = "none"; // guard against double clicks
    try {
      if (Bridge.available) {
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

  // Quick commands
  quickButtons.forEach((button) =>
    button.addEventListener("click", () => {
      const label = button.getAttribute("data-command");
      if (Bridge.available) {
        onQuickCommand(button);
      } else {
        simulateQuickCommand(label);
      }
    }),
  );

  // Send form
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const hexCommand = commandInput.value.trim();

    if (Bridge.available) {
      if (!hexCommand) {
        appendLog("warning", "Cannot send: command is empty.");
        commandInput.focus();
        return;
      }
      onSend(hexCommand);
      commandInput.value = "";
      commandInput.focus();
    } else {
      simulateSend(hexCommand);
      commandInput.value = "";
      commandInput.focus();
    }
  });

  // Clear logs
  clearLogsButton.addEventListener("click", () => {
    terminalLogs.replaceChildren();
  });

  // Modal events
  if (modalCopy) {
    modalCopy.addEventListener("click", copyModalResult);
  }
  if (modalClose) {
    modalClose.addEventListener("click", closeModal);
  }
  if (overlay) {
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) {
        closeModal();
      }
    });
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && overlay && !overlay.hidden) {
      closeModal();
    }
  });

  // Boot
  (async function boot() {
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
