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
            "subhead": "Lemma runs before account creation, so the business gets a reusable human signal without collecting identity documents.",
            "primary": "Start free trial",
            "protected": "Trial creation protected by isHuman",
            "success": "Trial workspace created for verified human",
            "risk": "Stops free-trial farms, promo abuse, and fake account swarms.",
            "business_value": "The SaaS company gets a stronger human signal without asking every trial user to upload ID documents.",
            "user_value": "The user reuses the same wallet proof and avoids another CAPTCHA or full IDV flow.",
            "form": "Work email",
            "placeholder": "founder@example.com",
        }
    return {
        "eyebrow": "Ticket release",
        "headline": "Reserve 2 tickets for the sold-out drop",
        "subhead": "The ticketing site gates the high-abuse action with Lemma instead of another CAPTCHA puzzle.",
        "primary": "Reserve tickets",
        "protected": "Checkout queue protected by isHuman",
        "success": "Reservation held for verified human",
        "risk": "Stops account farms and scripted reservation attempts before checkout.",
        "business_value": "The ticketing business can reduce scalper automation without forcing every fan through another puzzle.",
        "user_value": "The fan proves humanness from their wallet instead of solving a brittle CAPTCHA at drop time.",
        "form": "Fan email",
        "placeholder": "fan@example.com",
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
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #eef2ff; color: #0f172a; }}
    header {{ background:#fff;border-bottom:1px solid #e2e8f0;padding:16px 24px;display:flex;justify-content:space-between;align-items:center }}
    header strong {{ font-size:18px }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 32px 18px; }}
    .hero {{ display:grid;grid-template-columns:1.2fr .8fr;gap:18px;align-items:stretch }}
    .panel {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 18px; padding: 26px; box-shadow:0 10px 28px rgba(15,23,42,.08) }}
    .dark {{ background: #0f172a; color: #e2e8f0; border-color:#334155 }}
    .dark h1 {{ color:#fff }}
    h1 {{ margin:0 0 10px;font-size:42px;line-height:1.05 }}
    .muted {{ color:#64748b }}
    .dark .muted {{ color:#cbd5e1 }}
    .field {{ margin-top:18px }}
    label {{ display:block;font-size:13px;font-weight:800;margin-bottom:6px;color:#334155 }}
    input {{ width:100%;box-sizing:border-box;border:1px solid #cbd5e1;border-radius:10px;padding:12px;font-size:15px }}
    button {{ border: 0; background: #4f46e5; color: #fff; border-radius: 10px; padding: 12px 16px; font-weight: 800; cursor: pointer; margin-top:16px }}
    .secondary {{ background:#fff;color:#1e293b;border:1px solid #cbd5e1 }}
    .pill {{ display: inline-block; border: 1px solid #cbd5e1; border-radius: 999px; padding: 4px 9px; font-size: 12px; font-weight: 800; background: #f8fafc; }}
    .ok {{ border-color: #86efac; background: #dcfce7; color: #166534; }}
    .deny {{ border-color: #fca5a5; background: #fee2e2; color: #991b1b; }}
    .decision {{ margin-top:18px;border:1px solid #dbeafe;background:#eff6ff;border-radius:12px;padding:14px }}
    .grid {{ display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:16px }}
    .value-grid {{ display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:16px }}
    .mini {{ background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:16px }}
    .mini h3 {{ margin:0 0 6px;font-size:16px }}
    pre {{ background: #0f172a; color: #dbeafe; padding: 12px; border-radius: 10px; overflow: auto; }}
    @media(max-width:850px){{ .hero,.grid,.value-grid{{grid-template-columns:1fr}} }}
  </style>
</head>
<body>
  <header>
    <strong>{SITE_NAME}</strong>
    <span class="pill">Lemma-enabled business site</span>
  </header>
  <main>
    <section class="hero">
      <div class="panel dark">
        <p style="font-size:12px;font-weight:800;letter-spacing:1.5px;text-transform:uppercase;color:#93c5fd;margin:0 0 8px">{copy["eyebrow"]}</p>
        <h1>{copy["headline"]}</h1>
        <p class="muted">{copy["subhead"]}</p>
        <div class="decision">
          <strong>{copy["protected"]}</strong>
          <p style="margin:6px 0 0;color:#334155">The site asks Lemma for a local verdict and a site-private PPID. It does not receive government ID data.</p>
        </div>
      </div>
      <div class="panel">
        <h2>Customer Action</h2>
        <p class="muted">{copy["risk"]}</p>
        <div class="field">
          <label>{copy["form"]}</label>
          <input value="{copy["placeholder"]}" aria-label="{copy["form"]}">
        </div>
        <button id="verify-btn">{copy["primary"]}</button>
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
    <section class="mini">
      <pre id="result">{{}}</pre>
    </section>
  </main>
  <script src="{LEMMA_ORIGIN}/sdk/ishuman-verifier.js"></script>
  <script>
    const pill = document.getElementById('status-pill');
    const result = document.getElementById('result');
    document.getElementById('verify-btn').addEventListener('click', async () => {{
      pill.textContent = 'CHECKING';
      pill.className = 'pill';
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
        result.textContent = JSON.stringify(response, null, 2);
      }} catch (err) {{
        pill.textContent = 'ERROR';
        pill.className = 'pill deny';
        document.getElementById('decision-copy').textContent = 'Verification failed: ' + err.message;
        result.textContent = JSON.stringify({{ error: err.message }}, null, 2);
      }}
    }});
  </script>
</body>
</html>"""
    return Response(html, mimetype="text/html")
