/* ============================================================
   Software Update Tool — frontend interactivity
   Handles action buttons and the accessible modal dialog.
   ============================================================ */

(function () {
  "use strict";

  /* ---------- Changelog data (mirrors COMMIT_HISTORY.md) ---------- */

  // Badge metadata per change type (add / change / remove, plus fix).
  var CHANGELOG_TYPE_META = {
    added: { label: "Added", icon: "bi-plus-lg" },
    changed: { label: "Changed", icon: "bi-pencil-fill" },
    fixed: { label: "Fixed", icon: "bi-tools" },
    removed: { label: "Removed", icon: "bi-trash3-fill" },
  };

  // Commits grouped by release, newest first (source: COMMIT_HISTORY.md).
  var CHANGELOG_RELEASES = [
    {
      version: "Unreleased",
      date: "in development",
      entries: [
        {
          hash: "93176d3",
          date: "2026-09-17",
          author: "pvu0705",
          message: "Add function start with space",
          type: "added",
        },
        {
          hash: "6963b18",
          date: "2026-09-16",
          author: "pvu0705",
          message: "Refactor command runner and update mass update script",
          type: "changed",
        },
      ],
    },
    {
      version: "1.4.0",
      date: "2026-09-08",
      entries: [
        {
          hash: "1929842",
          date: "2026-09-08",
          author: "pvu0705",
          message: "update ver 1.4.0",
          type: "changed",
        },
      ],
    },
    {
      version: "1.3.0",
      date: "2026-09-07",
      entries: [
        {
          hash: "74645cd",
          date: "2026-09-07",
          author: "PhongVu0705",
          message: "update 1.3.0",
          type: "changed",
        },
        {
          hash: "8557d01",
          date: "2026-09-07",
          author: "PhongVu0705",
          message: "update 1.3.0",
          type: "changed",
        },
        {
          hash: "86d3a50",
          date: "2026-09-07",
          author: "PhongVu0705",
          message: "update mass reflash UI",
          type: "added",
        },
        {
          hash: "2f65b1e",
          date: "2026-09-07",
          author: "PhongVu0705",
          message: "update UI",
          type: "changed",
        },
      ],
    },
    {
      version: "1.2.0",
      date: "2026-09-04",
      entries: [
        {
          hash: "14f3af3",
          date: "2026-09-04",
          author: "pvu0705",
          message: "update version 1.2.0",
          type: "changed",
        },
        {
          hash: "81bc6d8",
          date: "2026-09-04",
          author: "pvu0705",
          message: "update lock function",
          type: "changed",
        },
        {
          hash: "ef9d19b",
          date: "2026-09-04",
          author: "pvu0705",
          message: "update UI",
          type: "changed",
        },
        {
          hash: "9b23941",
          date: "2026-09-03",
          author: "pvu0705",
          message: "update UI",
          type: "changed",
        },
        {
          hash: "e665ad5",
          date: "2026-09-03",
          author: "pvu0705",
          message: "fix bug main",
          type: "fixed",
        },
        {
          hash: "0514aa8",
          date: "2026-09-03",
          author: "pvu0705",
          message: "update mass update function",
          type: "changed",
        },
        {
          hash: "96ea0f0",
          date: "2026-08-28",
          author: "pvu0705",
          message: "update mass update function",
          type: "added",
        },
        {
          hash: "f96edbf",
          date: "2026-08-27",
          author: "pvu0705",
          message: "update mass update function",
          type: "added",
        },
        {
          hash: "c377f47",
          date: "2026-08-26",
          author: "pvu0705",
          message: "code final 2.0",
          type: "changed",
        },
      ],
    },
    {
      version: "1.0.0",
      date: "2026-08-25",
      entries: [
        {
          hash: "ec97c1b",
          date: "2026-08-25",
          author: "pvu0705",
          message: "add checking function",
          type: "added",
        },
        {
          hash: "44b2b84",
          date: "2026-08-25",
          author: "pvu0705",
          message: "offical code for 1.0.0",
          type: "changed",
        },
        {
          hash: "503e470",
          date: "2026-08-24",
          author: "pvu0705",
          message: "update code final",
          type: "changed",
        },
        {
          hash: "a4d28cf",
          date: "2026-08-24",
          author: "pvu0705",
          message: "update full",
          type: "changed",
        },
        {
          hash: "cbf6adb",
          date: "2026-08-24",
          author: "pvu0705",
          message: "udpate UI",
          type: "changed",
        },
        {
          hash: "d486f5c",
          date: "2026-08-24",
          author: "pvu0705",
          message: "add UI html",
          type: "added",
        },
        {
          hash: "79afd6b",
          date: "2026-08-24",
          author: "pvu0705",
          message: "udpate main and add terminal run",
          type: "added",
        },
        {
          hash: "194b5c2",
          date: "2026-08-24",
          author: "pvu0705",
          message: "udpate logic 2",
          type: "changed",
        },
        {
          hash: "3fca914",
          date: "2026-08-21",
          author: "pvu0705",
          message: "update UI 2",
          type: "changed",
        },
        {
          hash: "a7fdbd1",
          date: "2026-08-21",
          author: "pvu0705",
          message: "add UI",
          type: "added",
        },
        {
          hash: "fb03c8d",
          date: "2026-08-21",
          author: "pvu0705",
          message: "udapte code 2",
          type: "changed",
        },
        {
          hash: "82eeb73",
          date: "2026-08-21",
          author: "pvu0705",
          message: "update code",
          type: "changed",
        },
        {
          hash: "17a3d1e",
          date: "2026-08-20",
          author: "pvu0705",
          message: "init code",
          type: "added",
        },
      ],
    },
  ];

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function changelogBadgeHtml(type) {
    var meta = CHANGELOG_TYPE_META[type] || CHANGELOG_TYPE_META.changed;
    return (
      '<span class="changelog-badge is-' +
      type +
      '"><i class="bi ' +
      meta.icon +
      '" aria-hidden="true"></i>' +
      meta.label +
      "</span>"
    );
  }

  function changelogEntryHtml(entry) {
    return (
      '<li class="changelog-entry">' +
      changelogBadgeHtml(entry.type) +
      '<div class="changelog-entry-main">' +
      '<p class="changelog-message">' +
      escapeHtml(entry.message) +
      "</p>" +
      // '<p class="changelog-meta">' +
      // '<code class="changelog-hash">' +
      // escapeHtml(entry.hash) +
      // "</code>" +
      // '<span class="changelog-meta-sep">&middot;</span>' +
      // escapeHtml(entry.date) +
      // '<span class="changelog-meta-sep">&middot;</span>' +
      // escapeHtml(entry.author) +
      // "</p>" +
      "</div>" +
      "</li>"
    );
  }

  function changelogReleaseHtml(release) {
    var isUnreleased = release.version === "Unreleased";
    var html =
      '<section class="changelog-release' +
      (isUnreleased ? " is-unreleased" : "") +
      '">' +
      '<header class="changelog-release-header">' +
      '<span class="changelog-version">' +
      escapeHtml(release.version) +
      "</span>" +
      '<span class="changelog-release-date">' +
      escapeHtml(release.date) +
      "</span>" +
      '<span class="changelog-release-count">' +
      release.entries.length +
      (release.entries.length === 1 ? " commit" : " commits") +
      "</span>" +
      "</header>" +
      '<ul class="changelog-list">';
    release.entries.forEach(function (entry) {
      html += changelogEntryHtml(entry);
    });
    html += "</ul></section>";
    return html;
  }

  function buildChangelogBody() {
    var usedTypes = {};
    var totalCommits = 0;
    var releaseCount = 0;

    CHANGELOG_RELEASES.forEach(function (release) {
      if (release.version !== "Unreleased") {
        releaseCount += 1;
      }
      totalCommits += release.entries.length;
      release.entries.forEach(function (entry) {
        usedTypes[CHANGELOG_TYPE_META[entry.type] ? entry.type : "changed"] =
          true;
      });
    });

    var legend = "";
    ["added", "changed", "fixed", "removed"].forEach(function (type) {
      if (usedTypes[type]) {
        legend += changelogBadgeHtml(type);
      }
    });

    var html =
      '<div class="changelog-summary">' +
      '<span class="changelog-summary-text">' +
      totalCommits +
      " commits &middot; " +
      releaseCount +
      " releases &middot; tracked in <code>COMMIT_HISTORY.md</code>" +
      "</span>" +
      '<span class="changelog-legend">' +
      legend +
      "</span>" +
      "</div>";

    CHANGELOG_RELEASES.forEach(function (release) {
      html += changelogReleaseHtml(release);
    });

    return html;
  }

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
        '<span class="about-version-badge" id="settingsLauncherVersion">1.4.0</span>' +
        "</div>",
    },

    changelog: {
      title: "Changelog",
      titleIcon: "bi-clock-history",
      body: buildChangelogBody(),
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
