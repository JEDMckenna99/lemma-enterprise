import {
  verifyRouteCredential,
  verifyPackageAgainstRoute,
  signDeliveryEvent,
  policyLabel,
} from "/static/js/shared/crypto-client.js";

function percentile(values, p) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const idx = Math.ceil((p / 100) * sorted.length) - 1;
  return sorted[Math.max(0, idx)];
}

async function runMode(mode, iterations, profile) {
  const bundle = window.DeliveryStorage.getBundle();
  if (!bundle || !bundle.packages?.length) throw new Error("Download route bundle first");
  const assignment = bundle.packages[0].assignment || bundle.packages[0];
  const times = [];
  let failures = 0;

  for (let i = 0; i < iterations; i += 1) {
    const t0 = performance.now();
    try {
      if (mode === "local-first") {
        await verifyRouteCredential(bundle.route_credential, bundle.route_credential.device_id);
        await verifyPackageAgainstRoute(assignment, bundle.route_credential);
      } else {
        window.NetworkSimulator.setProfile(profile);
        await window.NetworkSimulator.cloudConfirm({ package_id: assignment.package_id });
        await window.NetworkSimulator.cloudDeliver({ package_id: assignment.package_id });
      }
      times.push((performance.now() - t0) / 1000);
    } catch (_) {
      failures += 1;
    }
  }

  const avg = times.length ? times.reduce((a, b) => a + b, 0) / times.length : 0;
  return {
    mode,
    network_profile: profile,
    avg_sec: Number(avg.toFixed(3)),
    p95_sec: Number(percentile(times, 95).toFixed(3)),
    failures,
    iterations,
    failure_rate: Number((failures / iterations).toFixed(3)),
  };
}

document.getElementById("run-benchmark").addEventListener("click", async () => {
  const iterations = Number(document.getElementById("iterations").value || 10);
  const out = document.getElementById("benchmark-results");
  out.textContent = "Running...";
  const local = await runMode("local-first", iterations, "offline");
  const cloud = await runMode("cloud-check", iterations, "weak");
  const payload = { local_first: local, cloud_check: cloud };
  await fetch("/api/benchmark/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode: "comparison", network_profile: "mixed", results: payload }),
  });
  out.innerHTML = "<pre>" + JSON.stringify(payload, null, 2) + "</pre>";
});
