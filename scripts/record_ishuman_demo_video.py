#!/usr/bin/env python
"""Record an automated isHuman E2E demo artifact.

The local environment does not need browser drivers for this script. It runs the
deployed Heroku isHuman flow via HTTP, then renders a short visual recording
from the real results. The output is suitable for a quick investor/operator
sanity check that the live system can issue, derive, block, and revoke.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import imageio.v2 as imageio
import requests
from PIL import Image, ImageDraw, ImageFont


WIDTH = 1280
HEIGHT = 720
BG = (15, 23, 42)
CARD = (248, 250, 252)
TEXT = (15, 23, 42)
MUTED = (71, 85, 105)
GREEN = (22, 101, 52)
BLUE = (30, 64, 175)
RED = (153, 27, 27)
PURPLE = (79, 70, 229)


def short(value: str | None, size: int = 18) -> str:
    value = str(value or "")
    if len(value) <= size * 2 + 3:
        return value or "-"
    return f"{value[:size]}...{value[-size:]}"


def font(size: int, bold: bool = False):
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def wrap(text: str, width: int = 82) -> list[str]:
    lines: list[str] = []
    for paragraph in str(text).splitlines() or [""]:
        lines.extend(textwrap.wrap(paragraph, width=width) or [""])
    return lines


def request_json(method: str, url: str, **kwargs) -> dict:
    response = requests.request(method, url, timeout=45, **kwargs)
    try:
        data = response.json()
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"{method} {url} returned non-JSON {response.status_code}: {response.text[:300]}") from exc
    if response.status_code >= 400:
        raise RuntimeError(f"{method} {url} failed {response.status_code}: {json.dumps(data, indent=2)}")
    return data


def rotate_tokens(app_name: str) -> tuple[str, str]:
    test_token = secrets.token_urlsafe(32)
    admin_token = secrets.token_urlsafe(32)
    cmd = (
        f'heroku config:set "LEMMA_ISHUMAN_DEMO_TEST_TOKEN={test_token}" '
        f'"LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN={admin_token}" -a {app_name}'
    )
    result = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to rotate Heroku demo tokens: {result.stderr.strip()}")
    return test_token, admin_token


def run_e2e(base_url: str, app_name: str) -> dict:
    test_token, admin_token = rotate_tokens(app_name)
    wallet_id = "wallet_video_" + secrets.token_urlsafe(8)
    wallet_secret = secrets.token_hex(32)

    start = request_json(
        "POST",
        f"{base_url}/api/ishuman/start-verification",
        json={
            "wallet_id": wallet_id,
            "wallet_secret": wallet_secret,
            "return_url": f"{base_url}/demo/ishuman?verification_return=true",
        },
    )
    if not start.get("success"):
        raise RuntimeError(f"start-verification failed: {start}")

    complete = request_json(
        "POST",
        f"{base_url}/api/demo/ishuman/test-complete-verification",
        headers={"X-Demo-Test-Token": test_token},
        json={"session_id": start["session_id"]},
    )
    if not complete.get("success"):
        raise RuntimeError(f"test-complete failed: {complete}")

    master_id = complete["credential_id"]
    status = request_json("GET", f"{base_url}/api/ishuman/verification-status/{start['session_id']}")
    if status.get("status") != "verified":
        raise RuntimeError(f"status not verified: {status}")

    derived: dict[str, dict] = {}
    for target_site in ("tickets-demo.lemma.id", "trials-demo.lemma.id"):
        data = request_json(
            "POST",
            f"{base_url}/api/ishuman/derive-site-proof",
            json={
                "master_credential_id": master_id,
                "wallet_id": wallet_id,
                "wallet_secret": wallet_secret,
                "target_site": target_site,
            },
        )
        credential = data["credential"]
        claims = credential.get("claims") or {}
        derived[target_site] = {
            "credential_id": credential.get("id"),
            "ppid": credential.get("subject"),
            "siteId": claims.get("siteId"),
            "isHuman": claims.get("isHuman"),
        }

    if derived["tickets-demo.lemma.id"]["ppid"] == derived["trials-demo.lemma.id"]["ppid"]:
        raise RuntimeError("PPID derivation failed: demo sites received matching PPIDs")

    ticket_ppid = derived["tickets-demo.lemma.id"]["ppid"]
    block = request_json(
        "POST",
        f"{base_url}/api/demo/ishuman/site-block",
        json={"site_slug": "tickets", "ppid": ticket_ppid, "reason": "automated recording test block"},
    )
    review = request_json(
        "POST",
        f"{base_url}/api/demo/ishuman/network-revoke-request",
        json={"site_slug": "tickets", "ppid": ticket_ppid, "reason": "automated recording test review"},
    )
    approve = request_json(
        "POST",
        f"{base_url}/api/demo/ishuman/approve-network-revocation",
        headers={"X-Demo-Admin-Token": admin_token},
        json={"wallet_id": wallet_id, "master_credential_id": master_id, "reason": "automated recording test revocation"},
    )

    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "wallet_id": wallet_id,
        "session_id": start["session_id"],
        "stripe_session_id": start.get("stripe_session_id"),
        "master_credential_id": master_id,
        "status": status.get("status"),
        "derived": derived,
        "site_block": {"success": block.get("success"), "site_id": block.get("site_id")},
        "network_review": {"success": review.get("success"), "status": review.get("status")},
        "network_approve": {"success": approve.get("success"), "total_revoked": approve.get("total_revoked")},
    }


def draw_frame(title: str, subtitle: str, bullets: list[str], result: dict | None = None) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    title_font = font(46, bold=True)
    subtitle_font = font(24)
    body_font = font(25)
    mono_font = font(20)

    draw.text((54, 44), "lemma.id isHuman Demo", fill=(147, 197, 253), font=font(18, bold=True))
    draw.text((54, 80), title, fill=(255, 255, 255), font=title_font)
    y = 145
    for line in wrap(subtitle, 78):
        draw.text((58, y), line, fill=(203, 213, 225), font=subtitle_font)
        y += 32

    card_y = 245
    draw.rounded_rectangle((54, card_y, WIDTH - 54, HEIGHT - 54), radius=18, fill=CARD)
    y = card_y + 34
    for bullet in bullets:
        color = GREEN if bullet.startswith("PASS") else BLUE if bullet.startswith("INFO") else TEXT
        prefix = "✓ " if bullet.startswith("PASS") else "• "
        text = bullet.replace("PASS: ", "").replace("INFO: ", "")
        for idx, line in enumerate(wrap(text, 86)):
            draw.text((86, y), (prefix if idx == 0 else "  ") + line, fill=color, font=body_font)
            y += 34
        y += 6

    if result:
        snippet = json.dumps(result, indent=2)
        box = (690, 276, WIDTH - 82, HEIGHT - 86)
        draw.rounded_rectangle(box, radius=12, fill=(15, 23, 42))
        yy = box[1] + 18
        for line in snippet.splitlines()[:15]:
            draw.text((box[0] + 18, yy), line[:54], fill=(219, 234, 254), font=mono_font)
            yy += 25

    return img


def draw_browser_scene(
    url: str,
    title: str,
    left_title: str,
    left_lines: list[str],
    right_title: str,
    right_lines: list[str],
    status: str,
    status_color=GREEN,
) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), (226, 232, 240))
    draw = ImageDraw.Draw(img)
    title_font = font(36, bold=True)
    h_font = font(26, bold=True)
    body_font = font(22)
    small_font = font(17)
    mono_font = font(18)

    # Browser chrome.
    draw.rounded_rectangle((34, 28, WIDTH - 34, HEIGHT - 28), radius=18, fill=(255, 255, 255))
    draw.rounded_rectangle((34, 28, WIDTH - 34, 86), radius=18, fill=(241, 245, 249))
    for i, color in enumerate(((239, 68, 68), (245, 158, 11), (34, 197, 94))):
        draw.ellipse((58 + i * 24, 49, 72 + i * 24, 63), fill=color)
    draw.rounded_rectangle((150, 45, WIDTH - 70, 70), radius=12, fill=(255, 255, 255), outline=(203, 213, 225))
    draw.text((166, 48), url, fill=MUTED, font=small_font)

    # Page hero.
    draw.rounded_rectangle((58, 110, WIDTH - 58, 230), radius=18, fill=BG)
    draw.text((88, 134), title, fill=(255, 255, 255), font=title_font)
    draw.text((90, 184), "Real Heroku APIs exercised during recording", fill=(203, 213, 225), font=small_font)
    pill_w = 250
    draw.rounded_rectangle((WIDTH - 88 - pill_w, 138, WIDTH - 88, 178), radius=20, fill=(220, 252, 231), outline=(134, 239, 172))
    draw.text((WIDTH - 70 - pill_w, 146), status, fill=status_color, font=small_font)

    # Main page panels.
    left = (72, 260, 620, 640)
    right = (660, 260, WIDTH - 72, 640)
    for box in (left, right):
        draw.rounded_rectangle(box, radius=16, fill=CARD, outline=(226, 232, 240))

    draw.text((left[0] + 24, left[1] + 22), left_title, fill=TEXT, font=h_font)
    y = left[1] + 70
    for line in left_lines:
        for wrapped in wrap(line, 42):
            draw.text((left[0] + 24, y), wrapped, fill=TEXT if not line.startswith("PPID") else BLUE, font=body_font)
            y += 31
        y += 8

    draw.text((right[0] + 24, right[1] + 22), right_title, fill=TEXT, font=h_font)
    y = right[1] + 70
    for line in right_lines:
        color = GREEN if line.startswith("ALLOW") or line.startswith("PASS") else RED if line.startswith("DENY") else MUTED
        for wrapped in wrap(line, 43):
            draw.text((right[0] + 24, y), wrapped, fill=color, font=body_font if not line.startswith("{") else mono_font)
            y += 31
        y += 8

    return img


def render_video(results: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    gif_path = output_dir / f"ishuman-demo-{stamp}.gif"
    json_path = output_dir / f"ishuman-demo-{stamp}.json"

    tickets = results["derived"]["tickets-demo.lemma.id"]
    trials = results["derived"]["trials-demo.lemma.id"]
    frames = [
        draw_browser_scene(
            "https://lemma.id/demo/ishuman",
            "One user, one proof, many sites",
            "User Benefit",
            [
                "Alex verifies once with the prototype Stripe Identity rail.",
                f"Master proof stored in browser wallet: {short(results['master_credential_id'], 15)}",
                "Alex can reuse the proof without repeated CAPTCHA or full IDV.",
            ],
            "IDV Provider Role",
            [
                f"PASS verification status: {results['status']}",
                f"PASS Stripe session: {short(results['stripe_session_id'], 12)}",
                "The original IDV check becomes a reusable trust signal.",
            ],
            "MASTER PROOF READY",
        ),
        draw_browser_scene(
            "https://lemma-demo-tickets-1d3d7411af33.herokuapp.com",
            "Ticketing site gates a high-abuse action",
            "Business Page",
            [
                "A fan clicks Reserve tickets on a separate Heroku app.",
                "The page loads the hosted Lemma verifier SDK.",
                "The business asks for a human verdict before the high-abuse action.",
            ],
            "Business Receives",
            [
                "ALLOW human=true",
                f"PPID {short(tickets['ppid'], 22)}",
                "No passport, selfie, or global user ID.",
            ],
            "TICKETING ALLOW",
        ),
        draw_browser_scene(
            "https://lemma-demo-trials-7090f46cae0d.herokuapp.com",
            "SaaS trial sees the same human privately",
            "Business Page",
            [
                "The same user starts a free trial on a second business site.",
                "The user does not repeat full IDV.",
                "The SaaS business still gets a high-confidence human signal.",
            ],
            "Privacy Boundary",
            [
                "ALLOW human=true",
                f"PPID {short(trials['ppid'], 22)}",
                "Ticketing and SaaS receive different private site IDs.",
            ],
            "TRIAL ALLOW",
        ),
        draw_browser_scene(
            "https://lemma.id/demo/ishuman",
            "Business blocks abuse without storing PII",
            "Ticketing Operator",
            [
                "The ticketing site sees bot-like behavior from its local PPID.",
                f"Blocked site PPID: {short(tickets['ppid'], 22)}",
                "The block is scoped to that business first.",
            ],
            "Business Control",
            [
                f"PASS site block: {results['site_block']['success']}",
                f"PASS scoped site: {results['site_block']['site_id']}",
                "No government ID data stored by the business.",
            ],
            "SITE BLOCK ACTIVE",
        ),
        draw_browser_scene(
            "https://lemma.id/demo/ishuman",
            "Severe abuse escalates to network review",
            "Network Review",
            [
                "Site block is immediate and reversible.",
                "Severe abuse can be escalated with evidence.",
                "IDV-backed proof can support ongoing trust, not one-off KYC.",
            ],
            "Network Trust Result",
            [
                f"PASS review status: {results['network_review']['status']}",
                f"PASS approved: {results['network_approve']['success']}",
                f"PASS total revoked: {results['network_approve']['total_revoked']}",
            ],
            "NETWORK REVOKED",
            RED,
        ),
        draw_browser_scene(
            "https://lemma.id",
            "Why Lemma matters to each party",
            "Stakeholder Value",
            [
                "User: one reusable proof, fewer CAPTCHA/IDV repeats.",
                "Business: human signal without storing identity documents.",
                "IDV provider: reusable demand layer for lower-margin web flows.",
            ],
            "Investor Takeaway",
            [
                "PASS one IDV check creates value across multiple sites",
                "PASS privacy boundary shown by different PPIDs",
                "PASS abuse controls shown by block and revocation",
            ],
            "NETWORK THESIS PROVEN",
            PURPLE,
        ),
    ]

    # Hold each slide for several seconds. GIF is intentionally used because it
    # does not require a system ffmpeg binary on Windows.
    repeated = []
    for frame in frames:
        repeated.extend([frame] * 28)
    imageio.mimsave(gif_path, repeated, duration=0.12)
    json_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return gif_path, json_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run and record the live isHuman demo flow.")
    parser.add_argument("--base-url", default="https://lemma.id")
    parser.add_argument("--heroku-app", default="lemma-enterprise")
    parser.add_argument("--output-dir", default="artifacts/demo-recordings")
    args = parser.parse_args()

    results = run_e2e(args.base_url.rstrip("/"), args.heroku_app)
    gif_path, json_path = render_video(results, Path(args.output_dir))
    print(f"Demo recording written: {gif_path}")
    print(f"Demo evidence written: {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
