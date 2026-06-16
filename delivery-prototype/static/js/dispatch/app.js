(function () {
  "use strict";

  var form = document.getElementById("route-form");
  var result = document.getElementById("result");
  var qrLinks = document.getElementById("qr-links");

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    var fd = new FormData(form);
    var payload = {
      route_id: fd.get("route_id"),
      driver_id: fd.get("driver_id"),
      device_id: fd.get("device_id"),
      package_count: Number(fd.get("package_count") || 20),
      stops: String(fd.get("stops") || "").split(",").map(function (s) { return s.trim(); }).filter(Boolean),
      expires_hours: Number(fd.get("expires_hours") || 12),
      photo_required: !!form.querySelector('[name="photo_required"]').checked,
      signature_required: !!form.querySelector('[name="signature_required"]').checked,
      otp_required: !!form.querySelector('[name="otp_required"]').checked,
    };
    var res = await fetch("/api/routes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    var data = await res.json();
    result.classList.remove("hidden");
    result.innerHTML = "<h3>Route created: " + data.route_id + "</h3><pre>" + JSON.stringify(data.credential, null, 2) + "</pre>";
    qrLinks.classList.remove("hidden");
    qrLinks.innerHTML = '<a class="btn primary" href="/api/routes/' + data.route_id + '/qr-sheet" target="_blank">Print QR Sheet</a>';
  });
})();
