(function () {
  "use strict";

  if (!("serviceWorker" in navigator)) return;

  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/metrics/sw.js", { scope: "/metrics/" }).catch(function () {
      /* non-fatal */
    });
  });

  function updateOnlineBadge() {
    var el = document.getElementById("offline-badge");
    if (!el) return;
    el.textContent = navigator.onLine ? "Online" : "Offline — saves on device";
    el.classList.toggle("offline", !navigator.onLine);
  }

  window.addEventListener("online", updateOnlineBadge);
  window.addEventListener("offline", updateOnlineBadge);
  document.addEventListener("DOMContentLoaded", updateOnlineBadge);
})();
