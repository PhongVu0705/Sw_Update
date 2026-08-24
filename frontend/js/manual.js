/* ============================================================
   Software Update Tool — Manual Command Send screen (manual.html)
   Connection toggle, quick commands with result modal,
   simulated send/response.
   ============================================================ */

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  /* ---------- Element references ---------- */

  const form = $("command-form");
  const comPort = $("com-port");
  const connectButton = $("connect-button");
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

  /* ---------- State ---------- */

  let isConnected = false;
  let lastFocusedElement = null;

  /* ---------- Simulated device responses (terminal) ---------- */

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

  /* ---------- Structured results shown in the modal ---------- */

  const RESULTS = {
    "TARGET M18": [
      ["Target device", "M18 FUEL Impact Wrench"],
      ["Selection status", "Active"],
    ],
    "TARGET M12": [
      ["Target device", "M12 Impact Driver"],
      ["Selection status", "Active"],
    ],
    "AUTH DEFAULT_METCO": [
      ["Authentication", "OK"],
      ["Session", "Opened"],
      ["Access level", "Service"],
    ],
    "GET CALIBRATION": [
      ["Torque calibration", "8.2 Nm"],
      ["Offset register", "0x1F"],
      ["CRC check", "PASS"],
    ],
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
    "WIPE COUNTERS": [
      ["Counters", "Wiped"],
      ["Histograms", "Wiped"],
      ["Scope", "Current target only"],
    ],
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

  const log = (level, message) => {
    const line = document.createElement("p");
    line.className = `log-line log-${level}`;
    line.textContent = `[${timestamp()}] ${level.toUpperCase()}: ${message}`;
    terminalLogs.appendChild(line);
    terminalLogs.scrollTop = terminalLogs.scrollHeight;
  };

  /* ---------- Result modal ---------- */

  const openResultModal = (command) => {
    const rows = Object.prototype.hasOwnProperty.call(RESULTS, command)
      ? RESULTS[command]
      : [["Result", "OK"]];

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

    modalTitle.textContent = "Command Result";
    modalBody.innerHTML = `<p class="result-command">Command: <code>${escapeHtml(
      command,
    )}</code></p>${rowsHtml}`;

    lastFocusedElement = document.activeElement;
    overlay.hidden = false;
    document.body.style.overflow = "hidden";
    modalClose.focus();
  };

  const closeModal = () => {
    if (!overlay || overlay.hidden) {
      return;
    }

    overlay.hidden = true;
    document.body.style.overflow = "";

    if (lastFocusedElement && typeof lastFocusedElement.focus === "function") {
      lastFocusedElement.focus();
    }
    lastFocusedElement = null;
  };

  /* ---------- Connection ---------- */

  connectButton.addEventListener("click", () => {
    if (!isConnected && !comPort.value) {
      log("warning", "Cannot connect: no COM port selected.");
      comPort.focus();
      return;
    }

    isConnected = !isConnected;
    connectButton.classList.toggle("is-connected", isConnected);
    connectButton.textContent = isConnected ? "Disconnect" : "Connect";
    comPort.disabled = isConnected;

    log(
      isConnected ? "success" : "info",
      isConnected
        ? `Connected to device on ${comPort.value}`
        : "Disconnected from device",
    );
  });

  /* ---------- Quick commands: send + show result modal ---------- */

  quickButtons.forEach((button) =>
    button.addEventListener("click", () => {
      const command = button.getAttribute("data-command");

      if (!isConnected) {
        log("warning", "Cannot send: no device connected.");
        comPort.focus();
        return;
      }

      // Execute like a normal send (visible in the terminal)
      log("sent", `>> ${command}`);
      const response = Object.prototype.hasOwnProperty.call(RESPONSES, command)
        ? RESPONSES[command]
        : "OK";
      setTimeout(() => log("response", `<< ${response}`), 250);

      // Show the structured result in a modal
      openResultModal(command);
    }),
  );

  /* ---------- Send ---------- */

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const command = commandInput.value.trim();

    if (!isConnected) {
      log("warning", "Cannot send: no device connected.");
      comPort.focus();
      return;
    }

    if (!command) {
      log("warning", "Cannot send: command is empty.");
      commandInput.focus();
      return;
    }

    log("sent", `>> ${command}`);

    const response = Object.prototype.hasOwnProperty.call(RESPONSES, command)
      ? RESPONSES[command]
      : "OK";
    setTimeout(() => log("response", `<< ${response}`), 250);

    commandInput.value = "";
    commandInput.focus();
  });

  /* ---------- Clear logs ---------- */

  clearLogsButton.addEventListener("click", () => {
    terminalLogs.replaceChildren();
  });

  /* ---------- Modal events ---------- */

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
})();
