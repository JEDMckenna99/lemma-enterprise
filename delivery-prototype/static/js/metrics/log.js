(function () {
  "use strict";

  var selections = {
    stop_type: null,
    signal_quality: null,
    delayed_action: null,
    delay_bucket: null,
    retry_needed: null,
  };

  function updateTodayCount() {
    var el = document.getElementById("today-count");
    if (!el) return;
    var n = window.MetricsStorage.getTodayLogs().length;
    el.textContent = n ? (n + " delay event" + (n === 1 ? "" : "s") + " logged today") : "No events logged today yet";
  }

  function showShiftBanner() {
    var shift = window.MetricsStorage.getShift();
    var banner = document.getElementById("shift-banner");
    if (!banner) return;
    if (!shift || !shift.started_at) {
      banner.classList.add("hidden");
      return;
    }
    banner.classList.remove("hidden");
    banner.innerHTML = "<strong>Shift active</strong>" +
      (shift.route_type ? " · " + shift.route_type : "") +
      (shift.weather ? " · " + shift.weather : "") +
      " <a href='/metrics/start'>Edit</a>";
  }

  function restorePrefs() {
    var prefs = window.MetricsStorage.getPrefs();
    Object.keys(selections).forEach(function (field) {
      if (!prefs[field]) return;
      selections[field] = prefs[field];
      var grid = document.querySelector('.btn-grid[data-field="' + field + '"]');
      if (!grid) return;
      grid.querySelectorAll("button").forEach(function (btn) {
        btn.classList.toggle("selected", btn.getAttribute("data-value") === prefs[field]);
      });
    });
  }

  function savePrefs() {
    window.MetricsStorage.savePrefs({
      stop_type: selections.stop_type,
      signal_quality: selections.signal_quality,
    });
  }

  function clearActionSelections() {
    ["delayed_action", "delay_bucket", "retry_needed"].forEach(function (field) {
      selections[field] = null;
      var grid = document.querySelector('.btn-grid[data-field="' + field + '"]');
      if (grid) grid.querySelectorAll("button").forEach(function (b) { b.classList.remove("selected"); });
    });
  }

  document.querySelectorAll(".btn-grid").forEach(function (grid) {
    var field = grid.getAttribute("data-field");
    grid.querySelectorAll("button").forEach(function (btn) {
      btn.addEventListener("click", function () {
        grid.querySelectorAll("button").forEach(function (b) { b.classList.remove("selected"); });
        btn.classList.add("selected");
        selections[field] = btn.getAttribute("data-value");
        if (field === "stop_type" || field === "signal_quality") savePrefs();
        if (navigator.vibrate) navigator.vibrate(10);
      });
    });
  });

  document.getElementById("delay-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var status = document.getElementById("save-status");
    var shift = window.MetricsStorage.getShift();
    var payload = {
      route_type: (shift && shift.route_type) || "suburban",
      stop_type: selections.stop_type,
      signal_quality: selections.signal_quality,
      delayed_action: selections.delayed_action,
      delay_bucket: selections.delay_bucket,
      retry_needed: selections.retry_needed,
    };

    var check = window.MetricsValidate.validatePayload(payload);
    if (!check.valid) {
      status.innerHTML = "<p class='step-bad'>" + check.error + "</p>";
      return;
    }

    var log = window.MetricsValidate.normalizeLog(payload, shift);
    window.MetricsStorage.addLog(log);
    status.innerHTML = "<div class='toast-ok'>Saved · " + log.log_id + "</div>";
    updateTodayCount();
    clearActionSelections();

    if (navigator.vibrate) navigator.vibrate([20, 30, 20]);

    if (navigator.onLine) {
      fetch("/api/metrics/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(log),
      }).catch(function () { /* optional server echo */ });
    }
  });

  restorePrefs();
  showShiftBanner();
  updateTodayCount();
})();
