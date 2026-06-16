(function () {
  "use strict";

  var BUCKETS = window.MetricsValidate ? window.MetricsValidate.BUCKETS : {
    "0-2_sec": 1, "3-5_sec": 4, "6-10_sec": 8, "10-20_sec": 15, "20+_sec": 25, failed_retry: 20,
  };

  function aggregate(logs) {
    var total = logs.length;
    var byAction = {};
    var byStop = {};
    var bySignal = {};
    var retries = 0;
    var timeLost = 0;
    var worst = "0-2_sec";
    var worstVal = 0;

    logs.forEach(function (row) {
      var action = row.delayed_action || "other";
      var stop = row.stop_type || "other";
      var signal = row.signal_quality || "unknown";
      var bucket = row.delay_bucket || "0-2_sec";
      byAction[action] = (byAction[action] || 0) + 1;
      byStop[stop] = (byStop[stop] || 0) + 1;
      bySignal[signal] = (bySignal[signal] || 0) + 1;
      if (row.retry_needed) retries += 1;
      var secs = BUCKETS[bucket] || 0;
      timeLost += secs;
      if (secs > worstVal) {
        worstVal = secs;
        worst = bucket;
      }
    });

    function maxKey(obj) {
      var best = null;
      var count = 0;
      Object.keys(obj).forEach(function (key) {
        if (obj[key] > count) {
          count = obj[key];
          best = key;
        }
      });
      return best;
    }

    var weakShare = 0;
    if (total) {
      var weak = logs.filter(function (row) {
        return row.signal_quality === "weak" || row.signal_quality === "no_service";
      }).length;
      weakShare = Math.round((100 * weak) / total * 10) / 10;
    }

    return {
      total_delay_events: total,
      delay_events_by_action: byAction,
      delay_events_by_stop_type: byStop,
      delay_events_by_signal: bySignal,
      estimated_time_lost_seconds: timeLost,
      estimated_time_lost_minutes: Math.round((timeLost / 60) * 10) / 10,
      retry_count: retries,
      worst_delay_category: worst,
      weak_no_service_share_percent: weakShare,
      most_common_delayed_action: maxKey(byAction),
      most_common_stop_type: maxKey(byStop),
    };
  }

  window.MetricsAggregate = { aggregate: aggregate };
})();
