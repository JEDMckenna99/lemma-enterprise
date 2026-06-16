(function () {
  "use strict";

  async function renderQueue() {
    var list = document.getElementById("queue-list");
    var items = await window.DeliveryQueue.list();
    if (!items.length) {
      list.innerHTML = "<p class='muted'>No queued events.</p>";
      return;
    }
    list.innerHTML = items.map(function (item) {
      return [
        "<div class='panel'>",
        "<p><strong>" + item.event_id + "</strong> — " + item.package_id + "</p>",
        "<p>Status: " + item.status + "</p>",
        "<p>Created: " + item.timestamp + "</p>",
        "<p>Signature valid: " + (item.signature ? "yes" : "no") + "</p>",
        "<p>Previous hash: " + item.previous_event_hash + "</p>",
        "</div>",
      ].join("");
    }).join("");
  }

  document.getElementById("sync-now").addEventListener("click", async function () {
    var bundle = window.DeliveryStorage.getBundle();
    if (!bundle) return;
    var items = await window.DeliveryQueue.list();
    var queued = items.filter(function (i) { return i.status === "queued"; });
    if (!queued.length) {
      await renderQueue();
      return;
    }
    var res = await fetch("/api/sync/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ route_id: bundle.route_credential.route_id, events: queued }),
    });
    var data = await res.json();
    (data.results || []).forEach(function (row) {
      if (row.status === "synced") window.DeliveryQueue.markSynced(row.event_id);
    });
    await renderQueue();
  });

  renderQueue();
})();
