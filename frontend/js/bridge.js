/* ============================================================
   Software Update Tool — pywebview bridge
   Detects the Python API (window.pywebview.api) and provides
   event registration for callbacks pushed from Python via
   evaluate_js (window.onLogFromPy, window.onProgressFromPy, ...).
   Falls back gracefully when opened in a plain browser.
   ============================================================ */

(function () {
  "use strict";

  const listeners = {};

  function emit(event, args) {
    (listeners[event] || []).forEach((handler) => {
      try {
        handler(...args);
      } catch (err) {
        console.error(`[bridge] error in ${event} handler:`, err);
      }
    });
  }

  const Bridge = {
    /** True when running inside pywebview with a Python API. */
    available: false,
    /** Reference to window.pywebview.api once ready. */
    api: null,
    _readyPromise: null,

    /**
     * Wait for the pywebview API to be injected.
     * Resolves true (backend available) or false (plain browser).
     */
    init() {
      if (this._readyPromise) {
        return this._readyPromise;
      }

      this._readyPromise = new Promise((resolve) => {
        let settled = false;

        const settle = (found) => {
          if (settled) {
            return;
          }
          settled = true;
          if (found) {
            this.available = true;
            this.api = window.pywebview.api;
          }
          resolve(found);
        };

        const check = () => {
          if (settled) {
            return;
          }
          if (window.pywebview && window.pywebview.api) {
            settle(true);
          } else {
            setTimeout(check, 100);
          }
        };

        // pywebview fires 'pywebviewready' as soon as the API is injected
        window.addEventListener("pywebviewready", check);

        check();

        // Give up after 8s -> plain browser / simulation mode
        setTimeout(() => settle(false), 8000);
      });

      return this._readyPromise;
    },

    /**
     * Register a handler for an event pushed from Python.
     * The first registration also installs window.<event> so that
     * Python's evaluate_js("window.<event>(...)") reaches us.
     */
    on(event, handler) {
      if (!listeners[event]) {
        listeners[event] = [];
        window[event] = (...args) => emit(event, args);
      }
      listeners[event].push(handler);
    },
  };

  window.Bridge = Bridge;
})();
