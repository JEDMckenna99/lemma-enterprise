(function () {
  "use strict";

  var STORAGE_KEY = "field_metrics_logs_v1";
  var SHIFT_KEY = "field_metrics_shift_v1";
  var PREFS_KEY = "field_metrics_prefs_v1";

  window.MetricsStorage = {
    getLogs: function () {
      try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"); } catch (_) { return []; }
    },
    addLog: function (log) {
      var logs = this.getLogs();
      logs.push(log);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(logs));
      return log;
    },
    getShift: function () {
      try { return JSON.parse(localStorage.getItem(SHIFT_KEY) || "null"); } catch (_) { return null; }
    },
    saveShift: function (shift) {
      localStorage.setItem(SHIFT_KEY, JSON.stringify(shift));
    },
    getPrefs: function () {
      try { return JSON.parse(localStorage.getItem(PREFS_KEY) || "{}"); } catch (_) { return {}; }
    },
    savePrefs: function (prefs) {
      localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
    },
    getTodayLogs: function () {
      var today = new Date().toISOString().slice(0, 10);
      return this.getLogs().filter(function (row) {
        return String(row.timestamp || "").slice(0, 10) === today;
      });
    },
    exportCsv: function () {
      var logs = this.getLogs();
      var headers = [
        "log_id", "timestamp", "route_type", "stop_type", "signal_quality",
        "delayed_action", "delay_bucket", "retry_needed", "sensitive_data_collected",
      ];
      var rows = logs.map(function (row) {
        return headers.map(function (h) {
          return JSON.stringify(row[h] == null ? "" : row[h]);
        }).join(",");
      });
      return [headers.join(",")].concat(rows).join("\n");
    },
    downloadCsv: function () {
      var csv = this.exportCsv();
      var blob = new Blob([csv], { type: "text/csv" });
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = "field_metrics_" + new Date().toISOString().slice(0, 10) + ".csv";
      a.click();
      URL.revokeObjectURL(url);
    },
  };
})();
