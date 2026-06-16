(function () {
  "use strict";

  var form = document.getElementById("shift-form");
  var dateInput = form.querySelector('[name="date"]');
  dateInput.value = new Date().toISOString().slice(0, 10);

  var existing = window.MetricsStorage.getShift();
  if (existing) {
    if (existing.route_type) form.querySelector('[name="route_type"]').value = existing.route_type;
    if (existing.weather) form.querySelector('[name="weather"]').value = existing.weather;
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var fd = new FormData(form);
    window.MetricsStorage.saveShift({
      date: fd.get("date"),
      weather: fd.get("weather"),
      route_type: fd.get("route_type"),
      difficulty: fd.get("difficulty"),
      battery_start: Number(fd.get("battery_start") || 0),
      started_at: new Date().toISOString(),
    });
    window.location.href = "/metrics/log";
  });
})();
