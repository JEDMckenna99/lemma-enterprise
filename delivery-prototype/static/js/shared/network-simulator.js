(function () {
  "use strict";

  window.NetworkSimulator = {
    profile: "good",
    setProfile: function (value) {
      this.profile = value || "good";
    },
    cloudConfirm: async function (payload) {
      if (this.profile === "offline") {
        throw new Error("offline");
      }
      var res = await fetch("/api/cloud/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({}, payload, { network_profile: this.profile })),
      });
      var data = await res.json();
      if (!res.ok) {
        var err = new Error(data.error || "cloud_failed");
        err.data = data;
        throw err;
      }
      return data;
    },
    cloudDeliver: async function (payload) {
      if (this.profile === "offline") {
        throw new Error("offline");
      }
      var res = await fetch("/api/cloud/deliver", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({}, payload, { network_profile: this.profile })),
      });
      return res.json();
    },
  };
})();
