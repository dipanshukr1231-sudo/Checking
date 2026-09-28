
import os
import json
import time
import hmac
import hashlib
import sqlite3
from threading import Thread
from urllib.parse import parse_qsl

from flask import Flask, request, jsonify, render_template_string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEB_APP_URL = os.environ.get("WEB_APP_URL", "")
PORT = int(os.environ.get("PORT", "10000"))
DB_PATH = os.environ.get("DB_PATH", "device_verification.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")
if not WEB_APP_URL:
    raise RuntimeError("WEB_APP_URL is missing")

app = Flask(__name__)

HTML = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Device Verification</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    :root { color-scheme: light dark; }
    * { box-sizing: border-box; }
    body {
      margin:0; font-family:Arial,sans-serif;
      background:var(--tg-theme-bg-color,#f4f5f7);
      color:var(--tg-theme-text-color,#111);
    }
    .wrap { max-width:520px; margin:auto; padding:20px; }
    .card {
      background:var(--tg-theme-secondary-bg-color,#fff);
      border-radius:22px; padding:22px;
      box-shadow:0 8px 28px rgba(0,0,0,.08);
    }
    h1 { margin:0 0 8px; font-size:25px; }
    .muted { color:var(--tg-theme-hint-color,#777); }
    .status {
      margin:18px 0; padding:15px; border-radius:16px;
      background:rgba(0,0,0,.05);
    }
    .ok { background:#dff7e5; color:#146c2e; }
    .bad { background:#ffe1e1; color:#9d1c1c; }
    .row { display:flex; justify-content:space-between; gap:15px;
           padding:10px 0; border-bottom:1px solid rgba(128,128,128,.18); }
    .row:last-child { border-bottom:0; }
    button {
      width:100%; border:0; border-radius:14px; padding:14px;
      font-size:16px; font-weight:700; cursor:pointer;
      background:var(--tg-theme-button-color,#2481cc);
      color:var(--tg-theme-button-text-color,#fff);
    }
    .small { font-size:13px; }
    .hidden { display:none; }
  </style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <h1>🔐 Device Verification</h1>
    <p class="muted">Sample Mini App for testing one-device-per-account rules.</p>

    <div id="status" class="status">Preparing device scan…</div>

    <div id="details" class="hidden">
      <div class="row"><span>Platform</span><strong id="platform">-</strong></div>
      <div class="row"><span>Screen</span><strong id="screen">-</strong></div>
      <div class="row"><span>Language</span><strong id="language">-</strong></div>
      <div class="row"><span>Timezone</span><strong id="timezone">-</strong></div>
      <div class="row"><span>CPU threads</span><strong id="cpu">-</strong></div>
    </div>

    <p class="muted small">
      Note: a web Mini App cannot read IMEI, SIM number, MAC address, or device serial number.
      This demo uses a privacy-limited browser/device fingerprint plus Telegram user identity.
    </p>

    <button id="scan">🔍 Verify Device</button>
  </div>
</div>

<script>
const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }

function collectSignals() {
  const s = {
    userAgent: navigator.userAgent || "",
    platform: navigator.platform || "",
    language: navigator.language || "",
    languages: (navigator.languages || []).join(","),
    screen: `${screen.width}x${screen.height}x${screen.colorDepth}`,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "",
    timezoneOffset: new Date().getTimezoneOffset(),
    hardwareConcurrency: navigator.hardwareConcurrency || 0,
    deviceMemory: navigator.deviceMemory || 0,
    touchPoints: navigator.maxTouchPoints || 0
  };

  document.getElementById("platform").textContent = s.platform || "Unknown";
  document.getElementById("screen").textContent = s.screen;
  document.getElementById("language").textContent = s.language;
  document.getElementById("timezone").textContent = s.timezone;
  document.getElementById("cpu").textContent = s.hardwareConcurrency || "Unknown";
  document.getElementById("details").classList.remove("hidden");
  return s;
}

async function sha256(text) {
  const data = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(digest)].map(x => x.toString(16).padStart(2,"0")).join("");
}

async function verify() {
  const status = document.getElementById("status");
  status.className = "status";
  status.textContent = "🔄 Scanning and verifying…";

  try {
    const signals = collectSignals();
    const raw = JSON.stringify(signals);
    const fingerprint = await sha256(raw);

    const initData = tg?.initData || "";

    if (!initData) {
      throw new Error("Open this page from the Telegram Mini App button.");
    }

    const res = await fetch("/api/verify", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        init_data:initData,
        fingerprint:fingerprint,
        signals:signals
      })
    });

    const data = await res.json();

    if (data.ok) {
      status.className = "status ok";
      status.textContent = "✅ Device verified. This Telegram account is registered on this device.";
    } else {
      status.className = "status bad";
      status.textContent = "❌ Verification failed: " + (data.message || "Device already belongs to another account.");
    }
  } catch (e) {
    status.className = "status bad";
    status.textContent = "❌ " + e.message;
  }
}

document.getElementById("scan").addEventListener("click", verify);
collectSignals();
</script>
</body>
</html>
"""

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            fingerprint TEXT PRIMARY KEY,
            telegram_user_id TEXT NOT NULL,
            username TEXT,
            first_verified_at INTEGER NOT NULL,
            last_seen_at INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_user_id TEXT PRIMARY KEY,
            username TEXT,
            fingerprint TEXT,
            verified_at INTEGER
        )
    """)
    conn.commit()
    conn.close()

def validate_telegram_init_data(init_data: str):
    """Validate Telegram Mini App initData using Telegram's documented HMAC scheme."""
    if not init_data:
        return None

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    # data_check_string is alphabetically sorted key=value pairs.
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(pairs.items())
    )

    secret_key = hmac.new(
        b"WebAppData",
        BOT_TOKEN.encode(),
        hashlib.sha256
    ).digest()

    calculated = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calculated, received_hash):
        return None

    # Optional freshness check: reject very old initData.
    auth_date = int(pairs.get("auth_date", "0") or 0)
    if not auth_date or abs(int(time.time()) - auth_date) > 86400:
        return None

    user_raw = pairs.get("user")
    if not user_raw:
        return None

    try:
        return json.loads(user_raw)
    except json.JSONDecodeError:
        return None

@app.route("/")
def home():
    return render_template_string(HTML)

@app.route("/health")
def health():
    return "OK"

@app.post("/api/verify")
def verify():
    body = request.get_json(silent=True) or {}
    init_data = body.get("init_data", "")
    fingerprint = body.get("fingerprint", "").strip()

    if not fingerprint or len(fingerprint) != 64:
        return jsonify(ok=False, message="Invalid device fingerprint."), 400

    tg_user = validate_telegram_init_data(init_data)
    if not tg_user:
        return jsonify(ok=False, message="Telegram verification failed."), 401

    user_id = str(tg_user["id"])
    username = tg_user.get("username", "")

    conn = db()
    try:
        # Same physical/browser fingerprint already linked to another Telegram ID.
        row = conn.execute(
            "SELECT telegram_user_id FROM devices WHERE fingerprint=?",
            (fingerprint,)
        ).fetchone()

        if row and row["telegram_user_id"] != user_id:
            return jsonify(
                ok=False,
                message="This device is already verified for another Telegram account."
            ), 403

        # This Telegram ID already has another fingerprint.
        user_row = conn.execute(
            "SELECT fingerprint FROM users WHERE telegram_user_id=?",
            (user_id,)
        ).fetchone()

        now = int(time.time())

        if user_row and user_row["fingerprint"] != fingerprint:
            return jsonify(
                ok=False,
                message="This Telegram account is already linked to a different device."
            ), 403

        if not row:
            conn.execute(
                """INSERT INTO devices
                   (fingerprint, telegram_user_id, username, first_verified_at, last_seen_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (fingerprint, user_id, username, now, now)
            )
        else:
            conn.execute(
                "UPDATE devices SET last_seen_at=?, username=? WHERE fingerprint=?",
                (now, username, fingerprint)
            )

        if not user_row:
            conn.execute(
                """INSERT INTO users
                   (telegram_user_id, username, fingerprint, verified_at)
                   VALUES (?, ?, ?, ?)""",
                (user_id, username, fingerprint, now)
            )
        else:
            conn.execute(
                "UPDATE users SET username=?, verified_at=? WHERE telegram_user_id=?",
                (username, now, user_id)
            )

        conn.commit()
        return jsonify(ok=True, message="Device verified.")
    finally:
        conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton(
            "🔐 Verify My Device",
            web_app=WebAppInfo(url=WEB_APP_URL)
        )
    ]]
    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "Open the Mini App to scan the available browser/device signals "
        "and verify this Telegram account.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def run_web():
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

def main():
    init_db()
    Thread(target=run_web, daemon=True).start()

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))

    print("Bot + Mini App server started")
    application.run_polling()

if __name__ == "__main__":
    main()
