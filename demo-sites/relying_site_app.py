import os

from flask import Flask, Response


app = Flask(__name__)

SITE_ID = os.getenv("LEMMA_DEMO_SITE_ID", "tickets-demo.lemma.id")
SITE_NAME = os.getenv("LEMMA_DEMO_SITE_NAME", "Lemma Demo Site")
SITE_KIND = os.getenv("LEMMA_DEMO_SITE_KIND", "ticketing")
LEMMA_ORIGIN = os.getenv("LEMMA_ORIGIN", "https://lemma.id")


@app.get("/health")
def health():
    return {"success": True, "site_id": SITE_ID, "site_name": SITE_NAME}


@app.get("/")
def index():
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{SITE_NAME}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #f8fafc; color: #0f172a; }}
    main {{ max-width: 920px; margin: 0 auto; padding: 36px 18px; }}
    .hero {{ background: #0f172a; color: #e2e8f0; border-radius: 18px; padding: 28px; }}
    .hero h1 {{ color: #fff; margin: 0 0 8px; font-size: 34px; }}
    .card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 14px; padding: 18px; margin-top: 16px; }}
    button {{ border: 0; background: #4f46e5; color: #fff; border-radius: 10px; padding: 11px 15px; font-weight: 700; cursor: pointer; }}
    .pill {{ display: inline-block; border: 1px solid #cbd5e1; border-radius: 999px; padding: 4px 9px; font-size: 12px; font-weight: 800; background: #f8fafc; }}
    .ok {{ border-color: #86efac; background: #dcfce7; color: #166534; }}
    .deny {{ border-color: #fca5a5; background: #fee2e2; color: #991b1b; }}
    pre {{ background: #0f172a; color: #dbeafe; padding: 12px; border-radius: 10px; overflow: auto; }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <p style="font-size:12px;font-weight:800;letter-spacing:1.5px;text-transform:uppercase;color:#93c5fd;margin:0 0 8px">{SITE_KIND} relying site</p>
      <h1>{SITE_NAME}</h1>
      <p>This is a separate Heroku app acting as a third-party relying site. It loads the hosted Lemma isHuman verifier from <code>{LEMMA_ORIGIN}</code>.</p>
    </section>
    <section class="card">
      <h2>Human Gate <span class="pill" id="status-pill">WAITING</span></h2>
      <p>Site binding: <code id="site-id">{SITE_ID}</code></p>
      <button id="verify-btn">Verify with Lemma isHuman</button>
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
        result.textContent = JSON.stringify(response, null, 2);
      }} catch (err) {{
        pill.textContent = 'ERROR';
        pill.className = 'pill deny';
        result.textContent = JSON.stringify({{ error: err.message }}, null, 2);
      }}
    }});
  </script>
</body>
</html>"""
    return Response(html, mimetype="text/html")
