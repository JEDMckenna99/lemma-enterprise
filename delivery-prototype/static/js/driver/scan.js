import {
  verifyRouteCredential,
  verifyPackageAgainstRoute,
  signDeliveryEvent,
  policyLabel,
} from "/static/js/shared/crypto-client.js";

function eventId() {
  return "EVT-" + Math.random().toString(16).slice(2, 10).toUpperCase();
}

function renderResult(html) {
  document.getElementById("scan-result").innerHTML = html;
}

async function processScan(assignment) {
  const t0 = performance.now();
  const bundle = window.DeliveryStorage.getBundle();
  if (!bundle) {
    renderResult("<p class='step-bad'>Download route bundle first.</p>");
    return;
  }
  const mode = document.getElementById("verify-mode").value;
  const profile = document.getElementById("network-profile").value;
  window.NetworkSimulator.setProfile(profile);

  const credential = bundle.route_credential;
  const routeCheck = await verifyRouteCredential(credential, credential.device_id);
  const pkgCheck = await verifyPackageAgainstRoute(assignment, credential);
  let allowed = routeCheck.ok && pkgCheck.ok;
  let verifyMs = ((performance.now() - t0) / 1000).toFixed(2);

  if (mode === "cloud-check") {
    try {
      const cloudStart = performance.now();
      await window.NetworkSimulator.cloudConfirm({ package_id: assignment.package_id });
      await window.NetworkSimulator.cloudDeliver({ package_id: assignment.package_id });
      verifyMs = ((performance.now() - cloudStart) / 1000).toFixed(2);
    } catch (err) {
      renderResult(`<p class='step-bad'>Cloud-check failed: ${err.message}</p>`);
      return;
    }
  }

  const proof = {
    photo_hash: `fake_photo_hash_${assignment.package_id}`,
    requirements_met: true,
  };

  if (mode === "local-first" && allowed) {
    const prior = window.DeliveryStorage.getLastEvent();
    const unsigned = {
      event_id: eventId(),
      event_type: "DELIVERED",
      package_id: assignment.package_id,
      route_id: assignment.route_id,
      stop_id: assignment.stop_id,
      timestamp: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
      gps_precision_bucket: "within_50m",
      proof,
      device_id: credential.device_id,
    };
    const signed = await signDeliveryEvent(
      unsigned,
      bundle.device_private_key_hex,
      credential,
      prior,
    );
    window.DeliveryStorage.saveLastEvent(signed);
    if (profile === "offline") {
      await window.DeliveryQueue.add(signed);
    } else {
      await fetch("/api/sync/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ route_id: credential.route_id, events: [signed] }),
      });
    }
  }

  renderResult([
    "<h3>Scan result</h3>",
    `<p>Package: <strong>${assignment.package_id}</strong></p>`,
    `<p>Route match: ${pkgCheck.routeMatch ? "yes" : "no"}</p>`,
    `<p>Stop match: ${pkgCheck.stopMatch ? "yes" : "no"}</p>`,
    `<p>Credential valid: ${routeCheck.ok ? "yes" : "no"}</p>`,
    `<p>Policy required: ${policyLabel(pkgCheck.policy || {})}</p>`,
    `<p>Verification time: ${verifyMs} sec</p>`,
    `<p>Result: <span class='${allowed ? "step-ok" : "step-bad"}'>${allowed ? "allowed" : "blocked"}</span></p>`,
    `<p>Mode: ${mode} / Network: ${profile}</p>`,
  ].join(""));
}

document.getElementById("manual-scan").addEventListener("click", async () => {
  const bundle = window.DeliveryStorage.getBundle();
  const pkgId = document.getElementById("manual-package").value.trim();
  let assignment = null;
  if (bundle?.packages) {
    const row = bundle.packages.find(
      (p) => p.package_id === pkgId || p.assignment?.package_id === pkgId,
    );
    if (row?.assignment) assignment = row.assignment;
  }
  if (!assignment && bundle) {
    const pkg = (bundle.route_credential.packages || []).find((p) => p.package_id === pkgId);
    if (pkg) {
      assignment = {
        credential_type: "PackageAssignment",
        package_id: pkg.package_id,
        route_id: bundle.route_credential.route_id,
        stop_id: pkg.stop_id,
        policy: pkg.policy,
      };
    }
  }
  if (!assignment) {
    renderResult("<p class='step-bad'>Package not found in bundle.</p>");
    return;
  }
  await processScan(assignment);
});
