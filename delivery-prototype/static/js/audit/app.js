(function () {
  "use strict";

  document.getElementById("load-chain").addEventListener("click", async function () {
    var routeId = document.getElementById("route-id").value.trim() || "R-001";
    var view = document.getElementById("chain-view");
    view.textContent = "Loading...";
    var res = await fetch("/api/audit/chain/" + encodeURIComponent(routeId));
    var data = await res.json();
    if (!res.ok) {
      view.innerHTML = "<p class='step-bad'>" + (data.error || "Failed") + "</p>";
      return;
    }
    view.innerHTML = [
      "<h3>Route " + data.route_id + " — tamper free: " + (data.tamper_free ? "yes" : "no") + "</h3>",
      "<ul>",
      (data.steps || []).map(function (step) {
        return "<li class='" + (step.valid ? "step-ok" : "step-bad") + "'>" + step.step + ": " + step.detail + "</li>";
      }).join(""),
      "</ul>",
    ].join("");
  });
})();
