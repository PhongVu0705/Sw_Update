/* ============================================================
   Software Update Tool — frontend interactivity
   Handles action buttons and the accessible modal dialog.
   ============================================================ */

(function () {
  "use strict";

  /* ---------- Content shown in the modal per action ---------- */

  var ACTIONS = {
    about: {
      title: "About this software",
      body:
        "<p>The <strong>Software Update Tool</strong> simplifies firmware deployment and updates across target devices.</p>" +
        "<p>Made by Grey Le Phong Vu. Version 1.0.0.</p>",
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
    titleEl.textContent = content.title;
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

  // Close button
  if (closeButton) {
    closeButton.addEventListener("click", closeModal);
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
