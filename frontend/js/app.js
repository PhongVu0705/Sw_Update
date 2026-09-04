/* ============================================================
   Software Update Tool — frontend interactivity
   Handles action buttons and the accessible modal dialog.
   ============================================================ */

(function () {
  "use strict";

  /* ---------- Content shown in the modal per action ---------- */

  var ACTIONS = {
    about: {
      title: "About",
      titleIcon: "bi-file-earmark-person",
      body:
        '<div class="about-creator">' +
        '<span class="about-avatar">' +
        '<img src="img/images.jpg" alt="Avatar of Grey Le Phong Vu" />' +
        "</span>" +
        '<div class="about-creator-info">' +
        '<span class="about-creator-label">Creator</span>' +
        '<span class="about-creator-name">Grey Le Phong Vu</span>' +
        "</div>" +
        "</div>" +
        '<hr class="about-divider" />' +
        '<div class="about-version-card">' +
        '<div class="about-version-label">' +
        '<i class="bi bi-info-circle-fill" aria-hidden="true"></i>' +
        "<span>Software Hub Version</span>" +
        "</div>" +
        // Default badge; a launcher/backend integration may overwrite this.
        '<span class="about-version-badge" id="settingsLauncherVersion">1.2.0</span>' +
        "</div>",
    },
  };

  /* ---------- Element references ---------- */

  var overlay = document.getElementById("modal-overlay");
  var modal = overlay ? overlay.querySelector(".modal") : null;
  var titleEl = document.getElementById("modal-title");
  var bodyEl = document.getElementById("modal-body");
  var closeButton = overlay
    ? overlay.querySelector("[data-close-modal]")
    : null;

  var lastFocusedElement = null;

  /* ---------- Modal helpers ---------- */

  function openModal(actionKey) {
    var content = ACTIONS[actionKey];
    if (!content || !overlay) {
      return;
    }

    lastFocusedElement = document.activeElement;
    if (content.titleIcon) {
      // Render "icon + title" in the dialog header.
      titleEl.classList.add("has-icon");
      titleEl.innerHTML =
        '<i class="bi ' + content.titleIcon + '" aria-hidden="true"></i>';
      var titleLabel = document.createElement("span");
      titleLabel.textContent = content.title;
      titleEl.appendChild(titleLabel);
    } else {
      titleEl.textContent = content.title;
      titleEl.classList.remove("has-icon");
    }
    bodyEl.innerHTML = content.body;

    overlay.hidden = false;
    document.body.style.overflow = "hidden";

    if (closeButton) {
      closeButton.focus();
    }
  }

  function closeModal() {
    if (!overlay) {
      return;
    }

    overlay.hidden = true;
    document.body.style.overflow = "";

    if (lastFocusedElement && typeof lastFocusedElement.focus === "function") {
      lastFocusedElement.focus();
    }
    lastFocusedElement = null;
  }

  /* ---------- Event wiring ---------- */

  // Action cards
  var actionButtons = document.querySelectorAll("[data-action]");
  Array.prototype.forEach.call(actionButtons, function (button) {
    button.addEventListener("click", function () {
      openModal(button.getAttribute("data-action"));
    });
  });

  // Close buttons (header "X" and footer "Close")
  if (overlay) {
    Array.prototype.forEach.call(
      overlay.querySelectorAll("[data-close-modal]"),
      function (button) {
        button.addEventListener("click", closeModal);
      },
    );
  }

  // Click on the dark backdrop (but not inside the dialog)
  if (overlay) {
    overlay.addEventListener("click", function (event) {
      if (event.target === overlay) {
        closeModal();
      }
    });
  }

  // Escape key closes the modal
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && overlay && !overlay.hidden) {
      closeModal();
    }
  });

  // Basic focus trap while the modal is open
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Tab" || !overlay || overlay.hidden || !modal) {
      return;
    }

    var focusable = modal.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    if (focusable.length === 0) {
      return;
    }

    var first = focusable[0];
    var last = focusable[focusable.length - 1];

    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
})();
