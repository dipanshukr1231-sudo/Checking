import os
from flask import Flask, render_template_string
from threading import Thread

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEB_APP_URL = os.getenv("WEB_APP_URL")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is missing")

if not WEB_APP_URL:
    raise ValueError("WEB_APP_URL environment variable is missing")


# =========================
# MINI APP WEB SERVER
# =========================

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >
    <title>Sample Mini App</title>

    <style>
        body {
            margin: 0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: Arial, sans-serif;
            background: #f2f2f2;
        }

        .box {
            background: white;
            padding: 35px;
            border-radius: 20px;
            text-align: center;
            box-shadow: 0 8px 30px rgba(0,0,0,0.10);
        }

        h1 {
            margin: 0 0 10px;
        }

        p {
            color: #666;
        }
    </style>
</head>

<body>

    <div class="box">
        <h1>🚀 Sample Mini App</h1>
        <p>This is a sample Telegram Mini App.</p>
    </div>

</body>
</html>
"""


@app.route("/")
def home():
    return render_template_string(HTML)


@app.route("/health")
def health():
    return "OK"


def run_web_server():
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# =========================
# TELEGRAM BOT
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [
        [
            InlineKeyboardButton(
                "🚀 Open Mini App",
                web_app=WebAppInfo(url=WEB_APP_URL)
            )
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "Tap the button below to open the sample Mini App.",
        reply_markup=reply_markup
    )


# =========================
# START BOT
# =========================

def main():

    # Start Flask server in background
    Thread(
        target=run_web_server,
        daemon=True
    ).start()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    print("Bot started...")

    application.run_polling()


if __name__ == "__main__":
    main()
