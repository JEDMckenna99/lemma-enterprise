import os

from flask import Flask, Response


app = Flask(__name__)

SITE_ID = os.getenv("LEMMA_DEMO_SITE_ID", "tickets-demo.lemma.id")
SITE_NAME = os.getenv("LEMMA_DEMO_SITE_NAME", "Lemma Demo Site")
SITE_KIND = os.getenv("LEMMA_DEMO_SITE_KIND", "ticketing")
LEMMA_ORIGIN = os.getenv("LEMMA_ORIGIN", "https://lemma.id")
DEMO_HUB_URL = os.getenv("LEMMA_DEMO_HUB_URL", f"{LEMMA_ORIGIN}/demo/ishuman")


def _content():
    if "trial" in SITE_KIND.lower():
        return {
            "eyebrow": "SaaS free trial",
            "headline": "Start a 14-day Pro workspace",
            "subhead": "Protected by Lemma — verify once, reuse your human proof.",
            "primary": "Start free trial",
            "success": "Trial workspace created",
            "form": "Work email",
            "placeholder": "founder@example.com",
        }
    return {
        "eyebrow": "Ticket release",
        "headline": "Reserve 2 tickets for the drop",
        "subhead": "Protected by Lemma — no CAPTCHA, no ID documents stored here.",
        "primary": "Reserve tickets",
        "success": "Reservation held",
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
    :root {{
      --bg: #f8fafc;
      --ink: #0f172a;
      --muted: #64748b;
      --line: #e2e8f0;
      --brand: #4f46e5;
      --ok: #166534;
      --deny: #991b1b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
      background: var(--bg);
      color: var(--ink);
    }}
    header {{
      background: #fff;
      border-bottom: 1px solid var(--line);
      padding: 14px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    header strong {{ font-size: 17px; }}
    header a {{ color: var(--muted); font-size: 13px; text-decoration: none; }}
    main {{ max-width: 920px; margin: 0 auto; padding: 28px 18px 48px; }}
    .layout {{ display: grid; grid-template-columns: 1.1fr .9fr; gap: 18px; }}
    .card {{
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 24px;
      box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
    }}
    .eyebrow {{
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 1.4px;
      text-transform: uppercase;
      color: var(--brand);
      margin: 0 0 8px;
    }}
    h1 {{ margin: 0 0 10px; font-size: clamp(32px, 6vw, 44px); line-height: 1.05; letter-spacing: -0.5px; }}
    .muted {{ color: var(--muted); line-height: 1.55; margin: 0; }}
    label {{ display: block; font-size: 13px; font-weight: 700; margin: 18px 0 6px; }}
    input {{
      width: 100%;
      border: 1px solid #cbd5e1;
      border-radius: 10px;
      padding: 12px;
      font-size: 15px;
    }}
    button {{
      width: 100%;
      border: 0;
      background: var(--brand);
      color: #fff;
      border-radius: 10px;
      padding: 14px 16px;
      font-weight: 800;
      font-size: 15px;
      cursor: pointer;
      margin-top: 16px;
    }}
    button:disabled {{ opacity: 0.65; cursor: not-allowed; }}
    .pill {{
      display: inline-block;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 9px;
      font-size: 11px;
      font-weight: 800;
      background: #f8fafc;
    }}
    .pill.ok {{ border-color: #86efac; background: #dcfce7; color: var(--ok); }}
    .pill.deny {{ border-color: #fca5a5; background: #fee2e2; color: var(--deny); }}
    .pill.checking {{ border-color: #fde68a; background: #fef9c3; color: #854d0e; }}
    .verdict {{
      margin-top: 18px;
      border-radius: 14px;
      padding: 16px;
      background: #0f172a;
      color: #e2e8f0;
      min-height: 120px;
    }}
    .verdict strong {{ color: #fff; display: block; margin-bottom: 6px; }}
    .verdict .tiny {{ font-size: 12px; color: #94a3b8; margin: 0; line-height: 1.45; }}
    .how {{ margin: 0; padding-left: 18px; color: var(--muted); font-size: 14px; line-height: 1.55; }}
    .how li {{ margin-bottom: 8px; }}
    code {{ font-size: 12px; background: #f1f5f9; padding: 2px 6px; border-radius: 6px; }}
    details {{ margin-top: 14px; }}
    summary {{ cursor: pointer; font-weight: 700; color: #334155; }}
    pre {{
      background: #0f172a;
      color: #dbeafe;
      padding: 12px;
      border-radius: 10px;
      overflow: auto;
      font-size: 12px;
    }}
    @media (max-width: 820px) {{ .layout {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header>
    <strong>{SITE_NAME}</strong>
    <a href="{DEMO_HUB_URL}" target="_blank" rel="noopener">Lemma demo hub</a>
  </header>
  <main>
    <div class="layout">
      <section class="card">
        <p class="eyebrow">{copy["eyebrow"]}</p>
        <h1>{copy["headline"]}</h1>
        <p class="muted">{copy["subhead"]}</p>
        <label for="email">{copy["form"]}</label>
        <input id="email" value="{copy["placeholder"]}" aria-label="{copy["form"]}">
        <button id="verify-btn">{copy["primary"]}</button>
        <div class="verdict" id="decision-card">
          <strong>What happens when you click</strong>
          <p class="tiny">This page calls <code>IsHumanVerifier.verify()</code> with <code>autoProvision: true</code>. If your browser wallet has no Lemma proof yet, a Lemma popup opens for wallet unlock + one-time IDV. The site only receives <code>human</code>, a site-private <code>ppid</code>, and <code>reason</code>.</p>
        </div>
      </section>
      <aside class="card">
        <p class="eyebrow">Customer site view</p>
        <p class="muted">Site binding: <code id="site-id">{SITE_ID}</code></p>
        <p style="margin:12px 0 6px">Decision <span class="pill" id="status-pill">WAITING</span></p>
        <p class="muted" id="decision-copy">Click the protected action to run the SDK.</p>
        <ol class="how">
          <li>SDK checks Lemma wallet via hidden bridge iframe.</li>
          <li>No master proof → IDV popup on lemma.id.</li>
          <li>Proof exists → local Ed25519 verify in milliseconds.</li>
          <li>Business never sees passport, selfie, or cross-site ID.</li>
        </ol>
        <details>
          <summary>SDK result object</summary>
          <pre id="result">{{}}</pre>
        </details>
      </aside>
    </div>
  </main>
  <script src="{LEMMA_ORIGIN}/sdk/ishuman-verifier.js?v=1.2.3"></script>
  <script>
    const pill = document.getElementById('status-pill');
    const result = document.getElementById('result');
    const decisionCard = document.getElementById('decision-card');
    const decisionCopy = document.getElementById('decision-copy');
    let backgroundVerifier = null;

    function makeVerifier(autoProvision) {{
      return new IsHumanVerifier({{
        siteId: '{SITE_ID}',
        lemmaOrigin: '{LEMMA_ORIGIN}',
        autoProvision,
        debug: true,
      }});
    }}

    function applyVerdict(response, {{ silent = false }} = {{}}) {{
      pill.textContent = response.human ? 'HUMAN' : (response.reason === 'session_valid' ? 'HUMAN' : 'DENY');
      pill.className = 'pill ' + (response.human ? 'ok' : (silent ? 'checking' : 'deny'));
      if (response.human) {{
        decisionCopy.textContent = '{copy["success"]}. PPID: ' + (response.ppid || '').slice(0, 28) + '…';
        if (!silent) {{
          decisionCard.innerHTML = '<strong>{copy["success"]}</strong><p class="tiny">human=true · reason=' + response.reason + ' · ' + response.timeMs.toFixed(0) + 'ms · site-private PPID issued.</p>';
        }}
      }} else if (!silent) {{
        decisionCopy.textContent = 'Blocked. Reason: ' + response.reason;
        decisionCard.innerHTML = '<strong>Action blocked</strong><p class="tiny">reason=' + response.reason + (response.reason === 'idv_cancelled' ? ' — complete verification in the Lemma popup to continue.' : '') + '</p>';
      }} else if (response.reason === 'session_valid') {{
        decisionCopy.textContent = 'Returning visitor — verified from local session cache.';
      }} else {{
        decisionCopy.textContent = 'Click the protected action to verify (IDV runs once per browser).';
      }}
      result.textContent = JSON.stringify(response, null, 2);
    }}

    async function runBackgroundCheck() {{
      pill.textContent = 'CHECKING';
      pill.className = 'pill checking';
      try {{
        backgroundVerifier = makeVerifier(false);
        const response = await backgroundVerifier.checkStatus();
        if (response.human) {{
          applyVerdict(response, {{ silent: true }});
        }} else {{
          pill.textContent = 'READY';
          pill.className = 'pill';
          decisionCopy.textContent = 'Click the protected action to verify (IDV runs once per browser).';
          result.textContent = JSON.stringify(response, null, 2);
        }}
      }} catch (err) {{
        pill.textContent = 'READY';
        pill.className = 'pill';
        decisionCopy.textContent = 'Background check skipped: ' + err.message;
      }}
    }}

    runBackgroundCheck();

    document.getElementById('verify-btn').addEventListener('click', async () => {{
      const button = document.getElementById('verify-btn');
      button.disabled = true;
      pill.textContent = 'CHECKING';
      pill.className = 'pill checking';
      decisionCard.innerHTML = '<strong>Checking Lemma wallet…</strong><p class="tiny">If no human proof exists yet, Lemma opens a popup to complete IDV once. Returning visitors reuse a cached session or wallet unlock only.</p>';
      try {{
        if (backgroundVerifier) {{
          backgroundVerifier.destroy();
          backgroundVerifier = null;
        }}
        const verifier = makeVerifier(true);
        const response = await verifier.verify();
        verifier.destroy();
        applyVerdict(response);
      }} catch (err) {{
        pill.textContent = 'ERROR';
        pill.className = 'pill deny';
        decisionCopy.textContent = 'Verification failed: ' + err.message;
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
