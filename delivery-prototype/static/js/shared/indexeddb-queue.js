(function () {
  "use strict";

  const DB_NAME = "delivery_prototype_queue";
  const STORE = "events";

  function openDb() {
    return new Promise(function (resolve, reject) {
      var req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = function () {
        req.result.createObjectStore(STORE, { keyPath: "event_id" });
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error); };
    });
  }

  window.DeliveryQueue = {
    add: async function (event) {
      var db = await openDb();
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, "readwrite");
        tx.objectStore(STORE).put(Object.assign({ status: "queued" }, event));
        tx.oncomplete = function () { resolve(true); };
        tx.onerror = function () { reject(tx.error); };
      });
    },
    list: async function () {
      var db = await openDb();
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, "readonly");
        var req = tx.objectStore(STORE).getAll();
        req.onsuccess = function () { resolve(req.result || []); };
        req.onerror = function () { reject(req.error); };
      });
    },
    markSynced: async function (eventId) {
      var db = await openDb();
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, "readwrite");
        var store = tx.objectStore(STORE);
        var getReq = store.get(eventId);
        getReq.onsuccess = function () {
          var row = getReq.result;
          if (row) {
            row.status = "synced";
            store.put(row);
          }
        };
        tx.oncomplete = function () { resolve(true); };
        tx.onerror = function () { reject(tx.error); };
      });
    },
    clearSynced: async function () {
      var items = await window.DeliveryQueue.list();
      var db = await openDb();
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, "readwrite");
        var store = tx.objectStore(STORE);
        items.filter(function (i) { return i.status === "synced"; }).forEach(function (i) {
          store.delete(i.event_id);
        });
        tx.oncomplete = function () { resolve(true); };
        tx.onerror = function () { reject(tx.error); };
      });
    },
  };
})();
