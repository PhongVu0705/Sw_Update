/* ============================================================
   Software Update Tool — frontend interactivity
   Handles action buttons and the accessible modal dialog.
   ============================================================ */

(function () {
  "use strict";

  /* ---------- Changelog (parsed from COMMIT_HISTORY.md) ---------- */

  // Badge metadata per change type, keyed by the "Type" column values
  // used in COMMIT_HISTORY.md (add / change / fix / remove).
  var CHANGELOG_TYPE_META = {
    add: { label: "Add", icon: "bi-plus-lg" },
    change: { label: "Change", icon: "bi-pencil-fill" },
    fix: { label: "Fix", icon: "bi-tools" },
    remove: { label: "Remove", icon: "bi-trash3-fill" },
  };

  // Source document rendered by the Changelog modal (same folder as index.html).
  var CHANGELOG_MD_URL = "COMMIT_HISTORY.md";

  // Cached parsed entries; null until the first successful load.
  var changelogEntries = null;

  function normalizeChangeType(raw) {
    var type = String(raw || "")
      .trim()
      .toLowerCase();
    return CHANGELOG_TYPE_META[type] ? type : "change";
  }

  // Parse the markdown table: | hash | date | type | message |
  function parseCommitHistory(markdown) {
    var entries = [];
    String(markdown || "")
      .split(/\r?\n/)
      .forEach(function (line) {
        if (!/^\s*\|/.test(line)) {
          return;
        }
        var cells = line
          .trim()
          .replace(/^\|/, "")
          .replace(/\|$/, "")
          .split("|")
          .map(function (cell) {
            return cell.trim();
          });
        if (cells.length < 4) {
          return;
        }
        // Only accept rows whose first cell looks like a commit hash;
        // this skips the header and separator rows.
        if (!/^[0-9a-f]{7,40}$/i.test(cells[0])) {
          return;
        }
        entries.push({
          hash: cells[0],
          date: cells[1],
          type: normalizeChangeType(cells[2]),
          message: cells.slice(3).join(" | "),
        });
      });
    return entries;
  }

  // Group entries into releases. A release starts at a commit whose
  // message contains a semantic version (e.g. "update ver 1.4.0").
  // Entries above the first release marker are shown as "Unreleased".
  function groupEntriesByRelease(entries) {
    var releases = [];
    var current = null;

    entries.forEach(function (entry) {
      var versionMatch = entry.message.match(/(\d+\.\d+\.\d+)/);
      var mentionsRelease = /version|ver\b|update|official|offical|release|bump/i.test(
        entry.message,
      );

      if (versionMatch && mentionsRelease) {
        var version = versionMatch[1];
        if (!current || current.version !== version) {
          current = { version: version, date: entry.date, entries: [] };
          releases.push(current);
        }
      }

      if (!current) {
        current = { version: "Unreleased", date: entry.date, entries: [] };
        releases.push(current);
      }

      current.entries.push(entry);
    });

    return releases;
  }

  function loadChangelog() {
    if (changelogEntries) {
      bodyEl.innerHTML = buildChangelogBody(changelogEntries);
      return;
    }

    bodyEl.innerHTML =
      '<p class="changelog-loading"><i class="bi bi-arrow-repeat" ' +
      'aria-hidden="true"></i>Loading changelog&hellip;</p>';

    fetch(CHANGELOG_MD_URL)
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.text();
      })
      .then(function (text) {
        var parsed = parseCommitHistory(text);
        if (parsed.length === 0) {
          throw new Error("No commits found in " + CHANGELOG_MD_URL);
        }
        changelogEntries = groupEntriesByRelease(parsed);
        bodyEl.innerHTML = buildChangelogBody(changelogEntries);
      })
      .catch(function () {
        bodyEl.innerHTML =
          '<p class="changelog-error">' +
          '<i class="bi bi-exclamation-triangle-fill" aria-hidden="true"></i>' +
          "Could not load the changelog." +
          "</p>" +
          '<button class="modal-button" type="button" data-retry-changelog>' +
          "Retry" +
          "</button>";

        var retryButton = bodyEl.querySelector("[data-retry-changelog]");
        if (retryButton) {
          retryButton.addEventListener("click", function () {
            changelogEntries = null;
            loadChangelog();
          });
        }
      });
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function changelogBadgeHtml(type) {
    var meta = CHANGELOG_TYPE_META[type] || CHANGELOG_TYPE_META.change;
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

  function buildChangelogBody(releases) {
    var usedTypes = {};
    var totalCommits = 0;
    var releaseCount = 0;

    releases.forEach(function (release) {
      if (release.version !== "Unreleased") {
        releaseCount += 1;
      }
      totalCommits += release.entries.length;
      release.entries.forEach(function (entry) {
        usedTypes[entry.type] = true;
      });
    });

    var legend = "";
    ["add", "change", "fix", "remove"].forEach(function (type) {
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
      " releases &middot; from <code>COMMIT_HISTORY.md</code>" +
      "</span>" +
      '<span class="changelog-legend">' +
      legend +
      "</span>" +
      "</div>";

    releases.forEach(function (release) {
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
      // Filled in asynchronously by loadChangelog() when the modal opens.
      body: "",
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

    if (actionKey === "changelog") {
      loadChangelog();
    }

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
