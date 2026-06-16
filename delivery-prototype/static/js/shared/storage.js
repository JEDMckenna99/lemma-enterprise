(function () {
  "use strict";

  const BUNDLE_KEY = "delivery_route_bundle_v1";
  const LAST_EVENT_KEY = "delivery_last_event_v1";

  window.DeliveryStorage = {
    saveBundle(bundle) {
      localStorage.setItem(BUNDLE_KEY, JSON.stringify(bundle));
    },
    getBundle() {
      try {
        return JSON.parse(localStorage.getItem(BUNDLE_KEY) || "null");
      } catch (_) {
        return null;
      }
    },
    saveLastEvent(event) {
      localStorage.setItem(LAST_EVENT_KEY, JSON.stringify(event));
    },
    getLastEvent() {
      try {
        return JSON.parse(localStorage.getItem(LAST_EVENT_KEY) || "null");
      } catch (_) {
        return null;
      }
    },
  };
})();
