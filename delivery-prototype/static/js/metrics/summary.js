(function () {
  "use strict";

  document.getElementById("summary-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var fd = new FormData(e.target);
    var shift = window.MetricsStorage.getShift() || {};
    shift.summary = {
      total_stops: Number(fd.get("total_stops") || 0),
      total_packages: Number(fd.get("total_packages") || 0),
      shift_length_hours: Number(fd.get("shift_length_hours") || 0),
      battery_end: Number(fd.get("battery_end") || 0),
      notes: String(fd.get("notes") || "").slice(0, 500),
      ended_at: new Date().toISOString(),
    };
    window.MetricsStorage.saveShift(shift);
    alert("Shift summary saved on this device");
  });

  document.getElementById("export-csv").addEventListener("click", function () {
    window.MetricsStorage.downloadCsv();
  });
})();
