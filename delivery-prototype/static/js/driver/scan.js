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

function parseAssignmentFromQr(text) {
  try {
    const data = JSON.parse(String(text || "").trim());
    if (data && data.package_id && data.route_id) {
      return data;
    }
  } catch (_) {
    /* ignore */
  }
  return null;
}

let cameraStream = null;
let scanLock = false;

async function stopCamera() {
  if (cameraStream) {
    cameraStream.getTracks().forEach((track) => track.stop());
    cameraStream = null;
  }
  const video = document.getElementById("preview");
  if (video) video.srcObject = null;
  document.getElementById("start-camera")?.classList.remove("hidden");
  document.getElementById("stop-camera")?.classList.add("hidden");
}

async function startCameraScan() {
  const status = document.getElementById("camera-status");
  if (!("BarcodeDetector" in window)) {
    status.textContent = "Camera QR scan not supported in this browser. Use manual package ID or Chrome on Android.";
    return;
  }
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" } },
      audio: false,
    });
    const video = document.getElementById("preview");
    video.srcObject = cameraStream;
    await video.play();
    document.getElementById("start-camera").classList.add("hidden");
    document.getElementById("stop-camera").classList.remove("hidden");
    status.textContent = "Point camera at a dispatch QR label…";

    const detector = new BarcodeDetector({ formats: ["qr_code"] });
    const tick = async () => {
      if (!cameraStream || scanLock) return;
      try {
        const codes = await detector.detect(video);
        if (codes.length) {
          const assignment = parseAssignmentFromQr(codes[0].rawValue);
          if (assignment) {
            scanLock = true;
            await stopCamera();
            status.textContent = "QR read: " + assignment.package_id;
            await processScan(assignment);
            scanLock = false;
            return;
          }
        }
      } catch (_) {
        /* keep scanning */
      }
      if (cameraStream) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  } catch (err) {
    status.textContent = "Camera error: " + (err.message || "permission denied");
  }
}

async function processScan(assignment) {
  const t0 = performance.now();
  const bundle = window.DeliveryStorage.getBundle();
  if (!bundle) {
    renderResult("<p class='step-bad'>Download route bundle first on <a href='/driver'>Driver home</a>.</p>");
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
    `<p>Signature: ${assignment.signature ? "present" : "missing"}</p>`,
    `<p>Policy required: ${policyLabel(pkgCheck.policy || assignment.policy || {})}</p>`,
    `<p>Verification time: ${verifyMs} sec</p>`,
    `<p>Result: <span class='${allowed ? "step-ok" : "step-bad"}'>${allowed ? "allowed" : "blocked"}</span></p>`,
    `<p>Mode: ${mode} / Network: ${profile}</p>`,
  ].join(""));
}

function resolveManualAssignment(pkgId) {
  const bundle = window.DeliveryStorage.getBundle();
  if (!bundle) return null;
  if (bundle.packages) {
    const row = bundle.packages.find(
      (p) => p.package_id === pkgId || p.assignment?.package_id === pkgId,
    );
    if (row?.assignment) return row.assignment;
  }
  const pkg = (bundle.route_credential.packages || []).find((p) => p.package_id === pkgId);
  if (pkg) {
    return {
      credential_type: "PackageAssignment",
      package_id: pkg.package_id,
      route_id: bundle.route_credential.route_id,
      stop_id: pkg.stop_id,
      policy: pkg.policy,
    };
  }
  return null;
}

document.getElementById("start-camera").addEventListener("click", startCameraScan);
document.getElementById("stop-camera").addEventListener("click", stopCamera);

document.getElementById("manual-scan").addEventListener("click", async () => {
  const pkgId = document.getElementById("manual-package").value.trim();
  const assignment = resolveManualAssignment(pkgId);
  if (!assignment) {
    renderResult("<p class='step-bad'>Package not found in bundle.</p>");
    return;
  }
  await processScan(assignment);
});

window.addEventListener("beforeunload", stopCamera);
