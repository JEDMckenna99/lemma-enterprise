import os

from flask import Flask, Response


app = Flask(__name__)

SITE_ID = os.getenv("LEMMA_DEMO_SITE_ID", "tickets-demo.lemma.id")
SITE_NAME = os.getenv("LEMMA_DEMO_SITE_NAME", "Lemma Demo Site")
SITE_KIND = os.getenv("LEMMA_DEMO_SITE_KIND", "ticketing")
LEMMA_ORIGIN = os.getenv("LEMMA_ORIGIN", "https://lemma.id")


def _content():
    if "trial" in SITE_KIND.lower():
        return {
            "eyebrow": "SaaS free trial",
            "headline": "Start a 14-day Pro workspace trial",
            "subhead": "Create a workspace without another CAPTCHA or full ID check.",
            "primary": "Start free trial",
            "protected": "Trial creation requires a human proof.",
            "success": "Trial workspace created",
            "risk": "Stops free-trial farms, promo abuse, and fake account swarms.",
            "business_value": "The SaaS company gets a stronger human signal without asking every trial user to upload ID documents.",
            "user_value": "The user reuses the same wallet proof and avoids another CAPTCHA or full IDV flow.",
            "abuse_signal": "Example abuse signal: 40 trial workspaces from one browser pattern in 3 minutes.",
            "response": "Lemma response: block this site-private human ID and require fresh IDV before another trial.",
            "form": "Work email",
            "placeholder": "founder@example.com",
            "action": "create a workspace",
        }
    return {
        "eyebrow": "Ticket release",
        "headline": "Reserve 2 tickets for the sold-out drop",
        "subhead": "Join the drop without another bot puzzle.",
        "primary": "Reserve tickets",
        "protected": "Reservation requires a human proof.",
        "success": "Reservation held",
        "risk": "Stops account farms and scripted reservation attempts before checkout.",
        "business_value": "The ticketing business can reduce scalper automation without forcing every fan through another puzzle.",
        "user_value": "The fan proves humanness from their wallet instead of solving a brittle CAPTCHA at drop time.",
        "abuse_signal": "Example abuse signal: queue timing and reservation attempts faster than a human can perform.",
        "response": "Lemma response: block this site-private human ID and require fresh IDV before another reservation.",
        "form": "Fan email",
        "placeholder": "fan@example.com",
        "action": "reserve tickets",
    }


@app.get("/health")
def health():
    return {"success": True, "site_id": SITE_ID, "site_name": SITE_NAME}


@app.get("/")
def index():
    copy = _content()
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{SITE_NAME}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #f8fafc; color: #0f172a; }}
    header {{ background:#fff;border-bottom:1px solid #e2e8f0;padding:16px 28px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:5 }}
    header strong {{ font-size:18px }}
    nav {{ display:flex;gap:18px;color:#64748b;font-size:14px }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 34px 18px; }}
    .hero {{ display:grid;grid-template-columns:1.15fr .85fr;gap:22px;align-items:start }}
    .panel {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 18px; padding: 28px; box-shadow:0 10px 28px rgba(15,23,42,.07) }}
    .product {{ min-height: 420px; }}
    h1 {{ margin:0 0 12px;font-size:48px;line-height:1.02;letter-spacing:-1px }}
    h2 {{ margin:0 0 10px }}
    .muted {{ color:#64748b;line-height:1.55 }}
    .field {{ margin-top:20px }}
    label {{ display:block;font-size:13px;font-weight:800;margin-bottom:6px;color:#334155 }}
    input {{ width:100%;box-sizing:border-box;border:1px solid #cbd5e1;border-radius:10px;padding:12px;font-size:15px }}
    button {{ border: 0; background: #4f46e5; color: #fff; border-radius: 10px; padding: 13px 16px; font-weight: 800; cursor: pointer; margin-top:16px;width:100%;font-size:15px }}
    button:disabled {{ opacity:.7;cursor:not-allowed }}
    .secondary {{ background:#fff;color:#1e293b;border:1px solid #cbd5e1 }}
    .pill {{ display: inline-block; border: 1px solid #cbd5e1; border-radius: 999px; padding: 4px 9px; font-size: 12px; font-weight: 800; background: #f8fafc; }}
    .ok {{ border-color: #86efac; background: #dcfce7; color: #166534; }}
    .deny {{ border-color: #fca5a5; background: #fee2e2; color: #991b1b; }}
    .warn {{ border-color:#facc15;background:#fef9c3;color:#854d0e }}
    .decision {{ margin-top:18px;border:1px solid #dbeafe;background:#eff6ff;border-radius:12px;padding:14px }}
    .abuse {{ margin-top:16px;border:1px solid #fed7aa;background:#fff7ed;border-radius:12px;padding:14px;color:#7c2d12 }}
    .abuse strong {{ display:block;margin-bottom:4px }}
    .grid {{ display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:18px }}
    .value-grid {{ display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:18px }}
    .mini {{ background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:16px }}
    .mini h3 {{ margin:0 0 6px;font-size:16px }}
    .result {{ margin-top:16px;border-radius:14px;padding:18px;background:#0f172a;color:#e2e8f0;min-height:120px }}
    .result strong {{ color:#fff }}
    .tiny {{ font-size:12px;color:#94a3b8;margin-top:10px }}
    details {{ margin-top:18px }}
    summary {{ cursor:pointer;font-weight:800;color:#334155 }}
    pre {{ background: #0f172a; color: #dbeafe; padding: 12px; border-radius: 10px; overflow: auto; }}
    @media(max-width:850px){{ .hero,.grid,.value-grid{{grid-template-columns:1fr}} }}
  </style>
</head>
<body>
  <header>
    <strong>{SITE_NAME}</strong>
    <nav><span>Product</span><span>Pricing</span><span>Support</span></nav>
  </header>
  <main>
    <section class="hero">
      <div class="panel product">
        <p style="font-size:12px;font-weight:800;letter-spacing:1.5px;text-transform:uppercase;color:#4f46e5;margin:0 0 8px">{copy["eyebrow"]}</p>
        <h1>{copy["headline"]}</h1>
        <p class="muted">{copy["subhead"]}</p>
        <div class="field">
          <label>{copy["form"]}</label>
          <input value="{copy["placeholder"]}" aria-label="{copy["form"]}">
        </div>
        <button id="verify-btn">{copy["primary"]}</button>
        <p class="tiny">{copy["protected"]} If the wallet has no reusable proof yet, the user can verify once at Lemma.</p>
        <div class="result" id="decision-card">
          <strong>Waiting for protected action</strong>
          <p class="tiny">When the user clicks, this site calls the Lemma SDK and receives only a verdict, a site-private ID, and a reason.</p>
        </div>
      </div>
      <div class="panel">
        <h2>What this business gets</h2>
        <p class="muted">{copy["risk"]}</p>
        <div class="decision">
          <strong>No ID documents stored here.</strong>
          <p style="margin:6px 0 0;color:#334155">The site does not see the user's passport, selfie, or global identity. It sees a private site ID it can use for local policy.</p>
        </div>
        <div class="abuse">
          <strong>When behavior looks automated</strong>
          <p style="margin:0 0 8px">{copy["abuse_signal"]}</p>
          <p style="margin:0">{copy["response"]}</p>
        </div>
        <button class="secondary" onclick="window.open('{LEMMA_ORIGIN}/demo/ishuman','_blank')">Open Lemma wallet/demo</button>
      </div>
    </section>
    <section class="grid">
      <div class="mini">
        <h2>Business Decision <span class="pill" id="status-pill">WAITING</span></h2>
        <p>Site binding: <code id="site-id">{SITE_ID}</code></p>
        <p id="decision-copy" class="muted">No Lemma decision yet.</p>
      </div>
      <div class="mini">
        <h2>What the site receives</h2>
        <p class="muted">A boolean verdict, a site-private PPID, and a reason code.</p>
      </div>
    </section>
    <section class="value-grid">
      <div class="mini">
        <h3>User benefit</h3>
        <p class="muted">{copy["user_value"]}</p>
      </div>
      <div class="mini">
        <h3>Business benefit</h3>
        <p class="muted">{copy["business_value"]}</p>
      </div>
      <div class="mini">
        <h3>IDV provider role</h3>
        <p class="muted">The IDV provider powers the original trusted check; Lemma makes the resulting proof reusable across sites.</p>
      </div>
    </section>
    <details class="mini">
      <summary>Developer result object</summary>
      <pre id="result">{{}}</pre>
    </details>
  </main>
  <script src="{LEMMA_ORIGIN}/sdk/ishuman-verifier.js"></script>
  <script>
    const pill = document.getElementById('status-pill');
    const result = document.getElementById('result');
    const decisionCard = document.getElementById('decision-card');
    document.getElementById('verify-btn').addEventListener('click', async () => {{
      const button = document.getElementById('verify-btn');
      button.disabled = true;
      pill.textContent = 'CHECKING';
      pill.className = 'pill';
      decisionCard.innerHTML = '<strong>Checking Lemma wallet...</strong><p class="tiny">The customer site is requesting a local isHuman verdict.</p>';
      try {{
        const verifier = new IsHumanVerifier({{
          siteId: '{SITE_ID}',
          lemmaOrigin: '{LEMMA_ORIGIN}',
          debug: true
        }});
        const response = await verifier.verify();
        verifier.destroy();
        pill.textContent = response.human ? 'HUMAN' : 'DENY';
        pill.className = 'pill ' + (response.human ? 'ok' : 'deny');
        document.getElementById('decision-copy').textContent = response.human
          ? '{copy["success"]}. PPID: ' + (response.ppid || '').slice(0, 28) + '...'
          : 'Action blocked. Reason: ' + response.reason;
        decisionCard.innerHTML = response.human
          ? '<strong>{copy["success"]}</strong><p class="tiny">Business received human=true and a site-private ID. The protected action can continue.</p>'
          : '<strong>Action blocked</strong><p class="tiny">Reason: ' + response.reason + '. If the user has no proof yet, they verify once with Lemma.</p>';
        result.textContent = JSON.stringify(response, null, 2);
      }} catch (err) {{
        pill.textContent = 'ERROR';
        pill.className = 'pill deny';
        document.getElementById('decision-copy').textContent = 'Verification failed: ' + err.message;
        decisionCard.innerHTML = '<strong>Verification unavailable</strong><p class="tiny">' + err.message + '</p>';
        result.textContent = JSON.stringify({{ error: err.message }}, null, 2);
      }} finally {{
        button.disabled = false;
      }}
    }});
  </script>
</body>
</html>"""
    return Response(html, mimetype="text/html")
