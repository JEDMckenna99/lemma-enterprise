(function () {
  "use strict";

  var btn = document.getElementById("download-bundle");
  var status = document.getElementById("bundle-status");
  var routeInput = document.getElementById("route-id");

  btn.addEventListener("click", async function () {
    var routeId = routeInput.value.trim() || "R-001";
    status.textContent = "Downloading...";
    var res = await fetch("/api/routes/" + encodeURIComponent(routeId) + "/bundle");
    var data = await res.json();
    if (!res.ok) {
      status.textContent = data.error || "Failed";
      return;
    }
    window.DeliveryStorage.saveBundle(data);
    status.textContent = "Bundle saved for " + routeId + " (" + (data.packages || []).length + " packages)";
  });
})();
