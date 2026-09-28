
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
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

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
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <title>Device Verification</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    *{box-sizing:border-box}
    html,body{margin:0;min-height:100%;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
    body{
      min-height:100vh;
      background:linear-gradient(180deg,#f5f7fb 0%,#eef1f6 100%);
      color:#0d1326;
      display:flex;
      align-items:center;
      justify-content:center;
      padding:24px 16px;
    }
    .page{width:100%;max-width:520px}
    .card{
      background:rgba(255,255,255,.96);
      border:1px solid rgba(255,255,255,.9);
      border-radius:28px;
      padding:34px 24px 28px;
      text-align:center;
      box-shadow:0 18px 50px rgba(22,31,55,.13);
    }
    .icon{
      width:92px;height:92px;border-radius:50%;
      margin:0 auto 24px;
      display:flex;align-items:center;justify-content:center;
      background:#edf0f4;
      color:#14213d;
      position:relative;
    }
    .shield{
      width:48px;height:54px;
      border:4px solid currentColor;
      border-radius:20px 20px 25px 25px;
      position:relative;
      clip-path:polygon(50% 0,92% 17%,88% 61%,73% 82%,50% 100%,27% 82%,12% 61%,8% 17%);
    }
    .shield:after{
      content:"";position:absolute;width:13px;height:7px;
      border-left:4px solid currentColor;border-bottom:4px solid currentColor;
      transform:rotate(-45deg);left:14px;top:18px;
    }
    .spinner{
      width:48px;height:48px;border:5px solid #d6dbe3;
      border-top-color:#19233d;border-radius:50%;
      animation:spin .9s linear infinite;
    }
    @keyframes spin{to{transform:rotate(360deg)}}
    .success{
      background:#e7f7ec;
      color:#17843b;
    }
    .success .shield{border-color:#17843b}
    h1{font-size:28px;line-height:1.15;margin:0 0 12px;font-weight:750;letter-spacing:-.5px}
    .message{font-size:17px;line-height:1.45;color:#687386;margin:0 auto 26px;max-width:390px}
    .rule{font-size:15px;color:#748093;margin-top:4px}
    .rule b{color:#5e6879}
    .details{
      margin-top:22px;text-align:left;background:#f7f8fa;
      border-radius:18px;padding:14px 16px;display:none;
    }
    .details.show{display:block}
    .row{display:flex;justify-content:space-between;gap:15px;padding:8px 0;font-size:14px}
    .row span{color:#7b8492}.row strong{font-weight:650;max-width:60%;text-align:right;word-break:break-word}
    .action{
      margin-top:24px;width:100%;border:0;border-radius:15px;padding:14px 18px;
      font-size:16px;font-weight:700;background:#17213b;color:white;cursor:pointer;
    }
    .action:disabled{opacity:.55;cursor:default}
    .error{
      margin-top:18px;padding:12px 14px;border-radius:14px;
      background:#fff0f0;color:#b42323;font-size:14px;display:none
    }
    .error.show{display:block}
    .foot{margin-top:15px;font-size:12px;color:#9aa2af;line-height:1.4}
    @media(prefers-reduced-motion:reduce){.spinner{animation:none}}
  </style>
</head>
<body>
<main class="page">
  <section class="card">
    <div id="icon" class="icon"><div class="shield"></div></div>

    <h1 id="title">Device Verification</h1>
    <p id="message" class="message">Aapka device check ho raha hai...</p>

    <div id="details" class="details">
      <div class="row"><span>Platform</span><strong id="platform">—</strong></div>
      <div class="row"><span>Screen</span><strong id="screen">—</strong></div>
      <div class="row"><span>Language</span><strong id="language">—</strong></div>
      <div class="row"><span>Timezone</span><strong id="timezone">—</strong></div>
    </div>

    <div id="error" class="error"></div>

    <p class="rule">Ek device par sirf <b>1 account</b> allowed hai 🚫</p>
    <button id="scan" class="action" type="button">🔐 Verify Device</button>
    <div class="foot">Secure sample verification • Telegram Mini App</div>
  </section>
</main>

<script>
const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }

function collectSignals(){
  const s={
    userAgent:navigator.userAgent||"",
    platform:navigator.platform||"",
    language:navigator.language||"",
    languages:(navigator.languages||[]).join(","),
    screen:`${screen.width}x${screen.height}x${screen.colorDepth}`,
    timezone:Intl.DateTimeFormat().resolvedOptions().timeZone||"",
    timezoneOffset:new Date().getTimezoneOffset(),
    hardwareConcurrency:navigator.hardwareConcurrency||0,
    deviceMemory:navigator.deviceMemory||0,
    touchPoints:navigator.maxTouchPoints||0
  };
  document.getElementById("platform").textContent=s.platform||"Unknown";
  document.getElementById("screen").textContent=s.screen;
  document.getElementById("language").textContent=s.language||"Unknown";
  document.getElementById("timezone").textContent=s.timezone||"Unknown";
  document.getElementById("details").classList.add("show");
  return s;
}

async function sha256(text){
  const data=new TextEncoder().encode(text);
  const digest=await crypto.subtle.digest("SHA-256",data);
  return [...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,"0")).join("");
}

async function verify(){
  const icon=document.getElementById("icon");
  const title=document.getElementById("title");
  const message=document.getElementById("message");
  const button=document.getElementById("scan");
  const error=document.getElementById("error");

  error.classList.remove("show");
  button.disabled=true;
  icon.className="icon";
  icon.innerHTML='<div class="spinner"></div>';
  title.textContent="Device Verification";
  message.textContent="Aapka device check ho raha hai...";

  try{
    const signals=collectSignals();
    const fingerprint=await sha256(JSON.stringify(signals));
    const initData=tg?.initData||"";
    if(!initData) throw new Error("Mini App ko Telegram ke andar se open karein.");

    const res=await fetch("/api/verify",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({init_data:initData,fingerprint,signals})
    });
    const data=await res.json();

    if(data.ok){
      icon.className="icon success";
      icon.innerHTML='<div class="shield"></div>';
      title.textContent="Device Verified";
      message.textContent="Device verified ✅ Redirecting you back to the bot...";
      button.style.display="none";

      // Give Telegram a moment to show the success state, then close
      // the Mini App and return the user to the bot chat.
      try {
        if (tg && typeof tg.sendData === "function") {
          tg.sendData(JSON.stringify({type:"device_verified"}));
        }
      } catch (_) {}

      setTimeout(() => {
        if (tg && typeof tg.close === "function") {
          tg.close();
        }
      }, 1200);
    }else{
      icon.className="icon";
      icon.innerHTML='<div class="shield" style="color:#b42323"></div>';
      title.textContent="Verification Failed";
      message.textContent=data.message||"This device is already linked to another account.";
      error.textContent="❌ Verification failed";
      error.classList.add("show");
      button.disabled=false;
      button.textContent="🔄 Try Again";
    }
  }catch(e){
    icon.className="icon";
    icon.innerHTML='<div class="shield" style="color:#b42323"></div>';
    title.textContent="Verification Failed";
    message.textContent=e.message||"Something went wrong.";
    error.textContent="❌ Please try again.";
    error.classList.add("show");
    button.disabled=false;
    button.textContent="🔄 Try Again";
  }
}

document.getElementById("scan").addEventListener("click",verify);
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


async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # The Mini App can send a small confirmation payload before closing.
    # The actual verification is already completed server-side.
    await update.message.reply_text(
        "✅ Device Verification Complete!\n\n"
        "Ab aap bot me wapas aa gaye hain. 🎉\n"
        "Aap next step continue kar sakte hain."
    )


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
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data))

    print("Bot + Mini App server started")
    application.run_polling()

if __name__ == "__main__":
    main()
