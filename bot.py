import os
import sqlite3
import asyncio
from datetime import datetime, timezone

import requests
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

TOKEN = os.getenv("BOT_TOKEN")
DB_FILE = "accounts.db"

# Instagram kontrol aralığı: 5 dakika
CHECK_INTERVAL = 300


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            username TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            status TEXT NOT NULL,
            last_checked TEXT,
            notified INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


def check_instagram(username):
    """
    Instagram profilinin erişilebilir olup olmadığını kontrol eder.
    Bu yöntem kesin bir hesap durumu garantisi vermez;
    Instagram erişim kısıtlamaları ve rate limit nedeniyle
    yanlış sonuç verebilir.
    """

    clean_username = username.replace("@", "")

    url = f"https://www.instagram.com/{clean_username}/"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=15,
            allow_redirects=True
        )

        if response.status_code == 200:
            return "active"

        if response.status_code in [404, 410]:
            return "unavailable"

        return "unknown"

    except requests.RequestException:
        return "unknown"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Bot is active!\n\n"
        "Add an account:\n"
        "/add @username\n\n"
        "Check an account:\n"
        "/status @username"
    )


async def add_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: /add @username"
        )
        return

    username = context.args[0].lower()

    if not username.startswith("@"):
        username = "@" + username

    started_at = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR REPLACE INTO accounts
        (username, started_at, status, last_checked, notified)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            username,
            started_at,
            "monitoring",
            None,
            0
        )
    )

    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"👻 Username: {username}\n"
        f"⏳ Status: Monitoring\n"
        f"🕐 Monitoring started: {started_at}"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: /status @username"
        )
        return

    username = context.args[0].lower()

    if not username.startswith("@"):
        username = "@" + username

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT username, started_at, status, last_checked
        FROM accounts
        WHERE username = ?
        """,
        (username,)
    )

    account = cursor.fetchone()
    conn.close()

    if not account:
        await update.message.reply_text(
            f"❌ No monitoring record found for {username}"
        )
        return

    await update.message.reply_text(
        f"👻 Username: {account[0]}\n"
        f"⏳ Status: {account[2]}\n"
        f"🕐 Started: {account[1]}\n"
        f"🔍 Last checked: {account[3] or 'Not checked yet'}"
    )


async def monitor_accounts(context: ContextTypes.DEFAULT_TYPE):
    """
    Tüm kayıtlı hesapları kontrol eder.
    """

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT username, started_at, status, notified
        FROM accounts
        """
    )

    accounts = cursor.fetchall()

    for username, started_at, current_status, notified in accounts:

        if current_status != "monitoring":
            continue

        result = check_instagram(username)

        now = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            """
            UPDATE accounts
            SET last_checked = ?
            WHERE username = ?
            """,
            (now, username)
        )

        conn.commit()

        # Instagram hâlâ erişilebilir
        if result == "active":
            continue

        # Sonuç kesin değilse bildirim gönderme
        if result == "unknown":
            continue

        # Hesap erişilemez hale geldiyse
        if result == "unavailable" and notified == 0:

            start_time = datetime.fromisoformat(started_at)

            elapsed = (
                datetime.now(timezone.utc) - start_time
            )

            total_seconds = int(elapsed.total_seconds())

            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            minutes = (total_seconds % 3600) // 60

            message = (
                "🚨 Instagram Status Change Detected\n\n"
                f"👻 Username: {username}\n"
                "⛔ Status: Unavailable\n"
                f"⏱️ Time monitored: "
                f"{days} days, {hours} hours, {minutes} minutes\n"
                f"🕐 Monitoring started: {started_at}\n"
                f"🔍 Detected at: {now}"
            )

            # Bot sahibine mesaj gönder
            chat_id = context.application.bot_data.get("chat_id")

            if chat_id:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=message
                )

            cursor.execute(
                """
                UPDATE accounts
                SET status = ?, notified = ?
                WHERE username = ?
                """,
                (
                    "unavailable",
                    1,
                    username
                )
            )

            conn.commit()

    conn.close()


async def save_chat_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """
    Botun mesaj göndereceği Telegram chat ID'sini kaydeder.
    """

    context.application.bot_data["chat_id"] = (
        update.effective_chat.id
    )

    await update.message.reply_text(
        "✅ Chat ID saved. Automatic monitoring notifications "
        "will be sent here."
    )


def main():

    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN environment variable is missing."
        )

    init_db()

    app = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("add", add_account)
    )

    app.add_handler(
        CommandHandler("status", status)
    )

    app.add_handler(
        CommandHandler("notify", save_chat_id)
    )

    # Her 5 dakikada bir Instagram hesaplarını kontrol et
    app.job_queue.run_repeating(
        monitor_accounts,
        interval=CHECK_INTERVAL,
        first=10
    )

    print("Bot is running...")

    app.run_polling()


if __name__ == "__main__":
    main()
