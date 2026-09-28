import os, json, time, hmac, hashlib, sqlite3
from threading import Thread
from urllib.parse import parse_qsl
from flask import Flask, jsonify, request, render_template_string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

BOT_TOKEN=os.getenv("BOT_TOKEN","").strip()
WEB_APP_URL=os.getenv("WEB_APP_URL","").strip()
PORT=int(os.getenv("PORT","10000"))
DB_PATH=os.getenv("DB_PATH","device_verification.db")

if not BOT_TOKEN: raise RuntimeError("BOT_TOKEN is missing")
if not WEB_APP_URL.startswith("https://"): raise RuntimeError("WEB_APP_URL must be an HTTPS Render URL")

def db():
    c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; return c

def init_db():
    c=db()
    c.execute("""CREATE TABLE IF NOT EXISTS devices(
        fingerprint TEXT PRIMARY KEY, telegram_user_id TEXT NOT NULL,
        username TEXT, first_verified_at INTEGER NOT NULL, last_seen_at INTEGER NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        telegram_user_id TEXT PRIMARY KEY, username TEXT,
        fingerprint TEXT, verified_at INTEGER)""")
    c.commit(); c.close()

def validate_init_data(init_data):
    try:
        if not init_data or len(init_data)>8192: return None
        pairs=parse_qsl(init_data,keep_blank_values=True,strict_parsing=True)
        data=dict(pairs); received=data.pop("hash",None)
        if not received or len(received)!=64: return None
        check="\n".join(f"{k}={data[k]}" for k in sorted(data))
        secret=hmac.new(b"WebAppData",BOT_TOKEN.encode(),hashlib.sha256).digest()
        calc=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc,received): return None
        auth_date=int(data.get("auth_date","0"))
        if not auth_date or abs(int(time.time())-auth_date)>86400: return None
        user=json.loads(data.get("user","{}"))
        return user if user.get("id") else None
    except (ValueError,TypeError,KeyError,json.JSONDecodeError):
        return None

HTML=r"""
<!doctype html>
<html lang="en" data-state="scanning">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>Device Verification</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
:root{
 --font:-apple-system,BlinkMacSystemFont,"SF Pro Text","Inter","Segoe UI",Roboto,Arial,sans-serif;
 --bg:#eef1f6;--card:#fff;--text:#111827;--muted:#6b7280;
 --accent:#2f80ed;--success:#16a34a;--danger:#dc2626;
 --tone:var(--accent);
}
:root[data-scheme=dark]{--bg:#0e1621;--card:#17212b;--text:#f5f7fa;--muted:#8793a3;--accent:#3f8ef5;--success:#34d399;--danger:#f87171}
:root[data-state=success]{--tone:var(--success)}
:root[data-state=failure]{--tone:var(--danger)}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:var(--bg);color:var(--text);
font-family:var(--font);-webkit-font-smoothing:antialiased}
.wrap{min-height:100vh;display:grid;place-items:center;padding:18px;position:relative;overflow:hidden}
.wrap:before{content:"";position:absolute;width:440px;height:440px;border-radius:50%;
background:color-mix(in srgb,var(--tone) 15%,transparent);filter:blur(80px);top:6%;left:50%;transform:translateX(-50%)}
.card{width:100%;max-width:410px;position:relative;padding:28px 24px 21px;border-radius:28px;
background:color-mix(in srgb,var(--card) 86%,transparent);backdrop-filter:blur(24px);
border:1px solid color-mix(in srgb,var(--text) 8%,transparent);
box-shadow:0 24px 65px color-mix(in srgb,#0f172a 20%,transparent),inset 0 1px 0 #fff9;
animation:in .7s ease both}
@keyframes in{from{opacity:0;transform:translateY(14px) scale(.985)}to{opacity:1;transform:none}}
.emblem{width:132px;height:132px;display:block;margin:0 auto 3px}
.ring-track{fill:none;stroke:color-mix(in srgb,var(--text) 10%,transparent);stroke-width:3}
.ring{fill:none;stroke:var(--tone);stroke-width:3;stroke-linecap:round;stroke-dasharray:100 100;stroke-dashoffset:100;transition:.55s linear}
[data-state=scanning] .ring{opacity:1}
.halo{fill:color-mix(in srgb,var(--tone) 9%,transparent)}
[data-state=scanning] .halo{animation:breathe 2.3s ease-in-out infinite}
@keyframes breathe{50%{transform:scale(1.06);opacity:1}}
.shield{fill:color-mix(in srgb,var(--tone) 10%,transparent);stroke:var(--tone);stroke-width:2.6}
.glyph{fill:none;stroke:var(--tone);stroke-linecap:round;stroke-linejoin:round}
.glyph-device{stroke-width:2.4}
.glyph-check,.glyph-cross{opacity:0;stroke-width:4.4;transition:.45s}
[data-state=success] .glyph-device,[data-state=failure] .glyph-device{opacity:0}
[data-state=success] .glyph-check,[data-state=failure] .glyph-cross{opacity:1}
.beam{fill:var(--tone);opacity:0}
[data-state=scanning] .beam{animation:beam 1.9s ease-in-out infinite}
@keyframes beam{15%{opacity:.65}85%{opacity:.65}100%{transform:translateY(68px);opacity:0}}
h1{margin:0;text-align:center;font-size:26px;line-height:1.15;letter-spacing:-.02em}
.sub{margin:9px auto 0;max-width:31ch;text-align:center;color:var(--muted);font-size:15px;line-height:1.5}
.steps{margin:24px auto 0;padding:0;max-width:305px;list-style:none}
.step{height:41px;display:flex;gap:13px;align-items:center;position:relative}
.step:not(:last-child):after{content:"";position:absolute;left:10px;top:29px;width:2px;height:24px;
background:color-mix(in srgb,var(--text) 10%,transparent);border-radius:2px}
.icon{width:21px;height:21px;position:relative;flex:none}
.dot,.spin,.tick,.cross{position:absolute;inset:0;margin:auto}
.dot{width:8px;height:8px;border-radius:50%;background:color-mix(in srgb,var(--text) 25%,transparent)}
.spin{width:18px;height:18px;border:2px solid color-mix(in srgb,var(--tone) 18%,transparent);
border-top-color:var(--tone);border-radius:50%;animation:rot .8s linear infinite;opacity:0}
@keyframes rot{to{transform:rotate(360deg)}}
.tick,.cross{width:21px;height:21px;border-radius:50%;display:grid;place-items:center;opacity:0}
.tick{background:color-mix(in srgb,var(--tone) 14%,transparent)}
.cross{background:color-mix(in srgb,var(--danger) 14%,transparent)}
.tick svg,.cross svg{width:12px;height:12px;fill:none;stroke-width:2.4;stroke-linecap:round}
.tick svg{stroke:var(--tone)}.cross svg{stroke:var(--danger)}
.step[data-status=active] .spin{opacity:1}
.step[data-status=done] .dot,.step[data-status=error] .dot{opacity:0}
.step[data-status=done] .tick,.step[data-status=error] .cross{opacity:1}
.label{font-size:15px;color:color-mix(in srgb,var(--text) 38%,transparent)}
.step[data-status=active] .label{color:var(--text)}
.step[data-status=done] .label{color:color-mix(in srgb,var(--text) 72%,transparent)}
.step[data-status=error] .label{color:var(--danger)}
.facts{margin-top:22px;padding:3px 15px;border-radius:16px;background:color-mix(in srgb,var(--text) 5%,transparent);text-align:left}
.fact{display:flex;justify-content:space-between;gap:15px;min-height:46px;align-items:center;font-size:14px}
.fact+.fact{border-top:1px solid color-mix(in srgb,var(--text) 7%,transparent)}
.fact span:first-child{color:var(--muted)}.fact span:last-child{font-weight:600;text-align:right;word-break:break-word}
.note{margin-top:20px;padding:12px 14px;border-radius:14px;color:color-mix(in srgb,var(--text) 80%,transparent);
background:color-mix(in srgb,var(--danger) 8%,transparent);border:1px solid color-mix(in srgb,var(--danger) 16%,transparent);
font-size:13.5px;line-height:1.5}
button{width:100%;min-height:54px;border:0;border-radius:16px;margin-top:18px;background:var(--accent);color:#fff;
font:600 16px var(--font);cursor:pointer;box-shadow:0 10px 24px color-mix(in srgb,var(--accent) 35%,transparent)}
button:disabled{opacity:.6;cursor:default}
.trust{margin-top:22px;padding-top:15px;border-top:1px solid color-mix(in srgb,var(--text) 7%,transparent);
display:flex;flex-wrap:wrap;justify-content:center;gap:8px 18px;color:var(--muted);font-size:12px}
@media(max-height:660px){.emblem{width:108px;height:108px}.card{padding-top:20px}.steps{margin-top:16px}}
</style>
</head>
<body>
<div class="wrap">
<main class="card">
<svg class="emblem" viewBox="0 0 140 140" aria-hidden="true">
<circle class="halo" cx="70" cy="70" r="46"/>
<circle class="ring-track" cx="70" cy="70" r="60"/>
<circle class="ring" id="ring" cx="70" cy="70" r="60" pathLength="100" transform="rotate(-90 70 70)"/>
<g>
<path class="shield" d="M70 33 95 42.5V68c0 17.5-10.5 30-25 38-14.5-8-25-20.5-25-38V42.5z"/>
<rect class="beam" x="44" y="39" width="52" height="10"/>
<g class="glyph glyph-device"><rect x="62" y="55" width="16" height="27" rx="3.5"/><path d="M67.5 77.5h5"/></g>
<path class="glyph glyph-check" d="m59 70 8 8 15-18"/>
<path class="glyph glyph-cross" d="m61 60 18 18M79 60 61 78"/>
</g>
</svg>

<h1 id="title">Device Verification</h1>
<p class="sub" id="sub">Your device is being securely checked. This usually takes just a few seconds.</p>

<ol class="steps" id="steps"></ol>

<section id="result" hidden>
  <div id="successFacts" class="facts">
    <div class="fact"><span>Reference ID</span><span id="ref">—</span></div>
    <div class="fact"><span>Verified at</span><span id="time">—</span></div>
  </div>
  <button id="continue">Continue</button>
</section>

<section id="failure" hidden>
  <p class="note" id="failureText"></p>
  <div class="facts" id="failureFacts" hidden>
    <div class="fact"><span>Reference ID</span><span id="badRef">—</span></div>
  </div>
  <button id="retry">Try Again</button>
</section>

<footer class="trust"><span>🔒 Secure Verification</span><span>📱 One account per device</span></footer>
</main>
</div>

<script>
(() => {
const tg=window.Telegram?.WebApp;
if(tg){tg.ready();tg.expand();}
const root=document.documentElement, ring=document.getElementById("ring");
const title=document.getElementById("title"), sub=document.getElementById("sub");
const steps=document.getElementById("steps"), result=document.getElementById("result");
const failure=document.getElementById("failure"), ref=document.getElementById("ref");
const timeEl=document.getElementById("time"), badRef=document.getElementById("badRef");
const failureText=document.getElementById("failureText"), failureFacts=document.getElementById("failureFacts");
const retry=document.getElementById("retry"), cont=document.getElementById("continue");
let busy=false;

const data=[
["Initializing secure check...",700],
["Analyzing device environment...",950],
["Checking device signature...",1000],
["Verifying Telegram account...",950],
["Finalizing verification...",850]
];

function theme(){
 const p=tg?.themeParams||{};
 const dark=(tg?.colorScheme||matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");
 root.dataset.scheme=dark;
 const map={bg_color:"--bg",secondary_bg_color:"--card",text_color:"--text",hint_color:"--muted",
 button_color:"--accent"};
 for(const [k,v] of Object.entries(map))if(p[k])root.style.setProperty(v,p[k]);
}
theme();tg?.onEvent?.("themeChanged",theme);

function build(){
 steps.innerHTML=data.map(x=>`<li class="step" data-status="pending">
 <span class="icon"><i class="dot"></i><i class="spin"></i><i class="tick"><svg viewBox="0 0 16 16"><path d="M3.5 8.6l3 3L12.5 5"/></svg></i><i class="cross"><svg viewBox="0 0 16 16"><path d="M4.5 4.5l7 7M11.5 4.5l-7 7"/></svg></i></span>
 <span class="label">${x[0]}</span></li>`).join("");
}

function signals(){
 return {
  userAgent:navigator.userAgent||"",platform:navigator.platform||"",
  language:navigator.language||"",screen:`${screen.width}x${screen.height}x${screen.colorDepth}`,
  timezone:Intl.DateTimeFormat().resolvedOptions().timeZone||"",
  hardwareConcurrency:navigator.hardwareConcurrency||0,
  touchPoints:navigator.maxTouchPoints||0
 };
}

async function hash(x){
 const d=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(JSON.stringify(x)));
 return [...new Uint8Array(d)].map(v=>v.toString(16).padStart(2,"0")).join("");
}

async function api(){
 if(!tg?.initData)throw Object.assign(new Error("Open this Mini App from Telegram."),{code:"CHECK_FAILED"});
 const s=signals(),fp=await hash(s);
 const r=await fetch("/v1/device/verify",{method:"POST",headers:{
  "Content-Type":"application/json","Authorization":"tma "+tg.initData
 },body:JSON.stringify({fingerprint:fp,signals:s})});
 const d=await r.json().catch(()=>({}));
 if(!r.ok)throw Object.assign(new Error(d.message||"Verification failed."),{
  code:d.code||"CHECK_FAILED",referenceId:d.referenceId||""
 });
 return d;
}

function progress(n){ring.style.strokeDashoffset=String(100-((n+1)/data.length)*100);}

async function run(){
 if(busy)return;busy=true;retry.disabled=true;root.dataset.state="scanning";
 result.hidden=true;failure.hidden=true;steps.hidden=false;
 title.textContent="Device Verification";
 sub.textContent="Your device is being securely checked. This usually takes just a few seconds.";
 [...steps.children].forEach(x=>x.dataset.status="pending");
 try{
  const pending=api();
  for(let i=0;i<data.length;i++){
   [...steps.children].forEach((x,j)=>x.dataset.status=j<i?"done":j===i?"active":"pending");
   progress(i);
   await new Promise(r=>setTimeout(r,data[i][1]));
  }
  const d=await pending;
  [...steps.children].forEach(x=>x.dataset.status="done");
  ring.style.strokeDashoffset="0";
  await new Promise(r=>setTimeout(r,450));

  root.dataset.state="success";steps.hidden=true;result.hidden=false;
  title.textContent="Device Verified";
  sub.textContent="Your device has been successfully verified.";
  ref.textContent=d.referenceId||"—";
  timeEl.textContent=new Date(d.verifiedAt||Date.now()).toLocaleString();

  // sendData closes the Mini App and returns the user to the bot chat.
  setTimeout(()=>{try{tg?.sendData?.(JSON.stringify({type:"device_verified"}));}catch(_){try{tg?.close?.()}catch(__){}}},1200);
 }catch(e){
  const active=[...steps.children].find(x=>x.dataset.status==="active");
  if(active)active.dataset.status="error";
  root.dataset.state="failure";steps.hidden=true;failure.hidden=false;
  title.textContent="Verification Failed";
  sub.textContent=e.message||"We couldn't verify this device.";
  failureText.textContent=e.code==="DEVICE_ALREADY_LINKED"
   ?"This device is already linked to another Telegram account. Each device can be linked to one account."
   :"Please try again. Check your connection if the problem continues.";
  if(e.referenceId){failureFacts.hidden=false;badRef.textContent=e.referenceId;}
  retry.disabled=false;
 }finally{busy=false;}
}
retry.onclick=run;
cont.onclick=()=>{try{tg?.sendData?.(JSON.stringify({type:"device_verified"}));}catch(_){}};
build();
setTimeout(run,500);
})();
</script>
</body>
</html>
"""

app=Flask(__name__)

@app.get("/")
def home():
    return render_template_string(HTML)

@app.get("/health")
def health():
    return "OK"

@app.post("/v1/device/verify")
def verify():
    auth=request.headers.get("Authorization","")
    if not auth.startswith("tma "):
        return jsonify(ok=False,code="AUTH_REQUIRED",message="Telegram authentication is required."),401
    user=validate_init_data(auth[4:].strip())
    if not user:
        return jsonify(ok=False,code="AUTH_FAILED",message="Telegram verification failed."),401

    body=request.get_json(silent=True) or {}
    fp=str(body.get("fingerprint","")).strip().lower()
    if len(fp)!=64 or any(c not in "0123456789abcdef" for c in fp):
        return jsonify(ok=False,code="CHECK_FAILED",message="Invalid device signature."),400

    uid=str(user["id"]); username=str(user.get("username") or ""); now=int(time.time())
    c=db()
    try:
        device=c.execute("SELECT * FROM devices WHERE fingerprint=?",(fp,)).fetchone()
        if device and device["telegram_user_id"]!=uid:
            ref="VRF-"+hashlib.sha256(f"{uid}:{now}".encode()).hexdigest()[:8].upper()
            return jsonify(ok=False,code="DEVICE_ALREADY_LINKED",
                           message="This device is already linked to another Telegram account.",
                           referenceId=ref),403

        current=c.execute("SELECT * FROM users WHERE telegram_user_id=?",(uid,)).fetchone()
        if current and current["fingerprint"] and current["fingerprint"]!=fp:
            ref="VRF-"+hashlib.sha256(f"{uid}:{now}:different".encode()).hexdigest()[:8].upper()
            return jsonify(ok=False,code="ACCOUNT_ALREADY_LINKED",
                           message="This Telegram account is already linked to a different device.",
                           referenceId=ref),403

        if not device:
            c.execute("INSERT INTO devices VALUES(?,?,?,?,?)",(fp,uid,username,now,now))
        else:
            c.execute("UPDATE devices SET username=?,last_seen_at=? WHERE fingerprint=?",(username,now,fp))

        c.execute("""INSERT INTO users(telegram_user_id,username,fingerprint,verified_at)
                     VALUES(?,?,?,?)
                     ON CONFLICT(telegram_user_id) DO UPDATE SET
                     username=excluded.username,fingerprint=excluded.fingerprint,verified_at=excluded.verified_at""",
                  (uid,username,fp,now))
        c.commit()

        reference="VRF-"+hashlib.sha256(f"{uid}:{fp}:{now}".encode()).hexdigest()[:8].upper()
        verified_at=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime(now))
        return jsonify(ok=True,status="verified",referenceId=reference,verifiedAt=verified_at)
    finally:
        c.close()

def web_server():
    app.run(host="0.0.0.0",port=PORT,debug=False,use_reloader=False)

async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):
    kb=[[InlineKeyboardButton("🔐 Verify My Device",web_app=WebAppInfo(url=WEB_APP_URL))]]
    await update.message.reply_text(
        "👋 Welcome!\n\nOpen the secure Mini App below to verify your device.",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def web_app_data(update:Update,context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Device Verification Complete!\n\nYour device has been verified successfully. 🎉"
    )

def main():
    init_db()
    Thread(target=web_server,daemon=True).start()
    bot=Application.builder().token(BOT_TOKEN).build()
    bot.add_handler(CommandHandler("start",start))
    bot.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA,web_app_data))
    print("✅ Bot + Mini App started")
    bot.run_polling()

if __name__=="__main__":
    main()
