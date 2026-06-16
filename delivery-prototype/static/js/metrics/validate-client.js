(function () {
  "use strict";

  var BUCKETS = {
    "0-2_sec": 1,
    "3-5_sec": 4,
    "6-10_sec": 8,
    "10-20_sec": 15,
    "20+_sec": 25,
    failed_retry: 20,
  };

  var SENSITIVE = ["package_id", "tracking", "address", "customer", "photo", "gps", "access_code", "tba"];

  function validatePayload(data) {
    if (!data || typeof data !== "object") {
      return { valid: false, error: "metrics payload must be object" };
    }
    var keys = Object.keys(data);
    for (var i = 0; i < keys.length; i += 1) {
      var lower = keys[i].toLowerCase();
      for (var j = 0; j < SENSITIVE.length; j += 1) {
        if (lower.indexOf(SENSITIVE[j]) !== -1) {
          return { valid: false, error: "sensitive field not allowed: " + keys[i] };
        }
      }
    }
    if (data.sensitive_data_collected === true) {
      return { valid: false, error: "sensitive_data_collected must be false" };
    }
    var required = ["stop_type", "signal_quality", "delayed_action", "delay_bucket", "retry_needed"];
    for (var k = 0; k < required.length; k += 1) {
      if (data[required[k]] == null || data[required[k]] === "") {
        return { valid: false, error: "missing " + required[k] };
      }
    }
    if (!Object.prototype.hasOwnProperty.call(BUCKETS, data.delay_bucket)) {
      return { valid: false, error: "invalid delay_bucket" };
    }
    return { valid: true };
  }

  function normalizeLog(data, shift) {
    return {
      log_id: data.log_id || ("LOG-" + Math.random().toString(16).slice(2, 10).toUpperCase()),
      timestamp: data.timestamp || new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
      route_type: data.route_type || (shift && shift.route_type) || "suburban",
      stop_type: String(data.stop_type),
      signal_quality: String(data.signal_quality),
      delayed_action: String(data.delayed_action),
      delay_bucket: String(data.delay_bucket),
      retry_needed: data.retry_needed === true || data.retry_needed === "true",
      sensitive_data_collected: false,
    };
  }

  window.MetricsValidate = {
    validatePayload: validatePayload,
    normalizeLog: normalizeLog,
    BUCKETS: BUCKETS,
  };
})();
