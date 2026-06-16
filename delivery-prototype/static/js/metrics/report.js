(function () {
  "use strict";

  function renderReport() {
    var logs = window.MetricsStorage.getTodayLogs();
    var data = window.MetricsAggregate.aggregate(logs);
    var shift = window.MetricsStorage.getShift();
    var stops = shift && shift.summary ? shift.summary.total_stops : 0;

    document.getElementById("report").innerHTML = [
      "<h3>Today</h3>",
      "<p>Logged delay events: <strong>" + data.total_delay_events + "</strong></p>",
      "<p>Estimated time lost: <strong>" + data.estimated_time_lost_minutes + " min</strong></p>",
      "<p>Retry count: " + data.retry_count + "</p>",
      "<p>Worst delay: " + data.worst_delay_category + "</p>",
      "<p>Most common action: " + (data.most_common_delayed_action || "n/a") + "</p>",
      "<p>Most common stop: " + (data.most_common_stop_type || "n/a") + "</p>",
      "<p>Weak/no-service: " + data.weak_no_service_share_percent + "%</p>",
      stops ? "<p>Events vs stops you entered: " + data.total_delay_events + " / " + stops + "</p>" : "",
      !navigator.onLine ? "<p class='muted'>Offline — totals from this phone only.</p>" : "",
    ].join("");

    if (navigator.onLine) {
      fetch("/api/metrics/aggregate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ logs: logs }),
      }).catch(function () { /* local report already shown */ });
    }
  }

  document.getElementById("refresh-report").addEventListener("click", renderReport);
  document.getElementById("export-csv").addEventListener("click", function () {
    window.MetricsStorage.downloadCsv();
  });

  renderReport();
})();
