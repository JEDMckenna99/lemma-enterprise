(function () {
  "use strict";

  window.DemoExplain = {
    set: function set(payload) {
      var el = document.getElementById("demo-with-lemma");
      if (!el) return;
      var decision = payload && payload.decision ? payload.decision.toUpperCase() : "UNKNOWN";
      var reason = payload && payload.reason_code ? payload.reason_code : "pending";
      var requestId = payload && payload.request_id ? payload.request_id : "-";
      el.innerHTML =
        "<strong>Decision:</strong> " + decision + "<br>" +
        "<strong>Reason code:</strong> " + reason + "<br>" +
        "<strong>Request:</strong> " + requestId + "<br>" +
        "<strong>Timestamp:</strong> " + new Date().toISOString();
    },
  };
})();
