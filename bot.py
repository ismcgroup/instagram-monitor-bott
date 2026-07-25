import os
import sqlite3
from datetime import datetime, timezone, timedelta

import requests
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

TOKEN = os.getenv("BOT_TOKEN")
DB_FILE = "accounts.db"

# Check every 5 minutes
CHECK_INTERVAL = 300

# Turkey time (UTC+3)
TURKEY_TZ = timezone(timedelta(hours=3))


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


def format_turkey_time(iso_time):
    dt = datetime.fromisoformat(iso_time)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    dt = dt.astimezone(TURKEY_TZ)

    return dt.strftime("%B %d, %Y at %I:%M %p").replace(" 0", " ")


def format_duration(seconds):
    seconds = int(seconds)

    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60

    parts = []

    if days:
        parts.append(f"{days} day" if days == 1 else f"{days} days")

    if hours:
        parts.append(f"{hours} hour" if hours == 1 else f"{hours} hours")

    if minutes:
        parts.append(
            f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"
        )

    if not parts:
        return "Less than 1 minute"

    return ", ".join(parts)


def check_instagram(username):
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
        "🤖 ISMC Bot is active!\n\n"
        "Start monitoring:\n"
        "/add @username\n\n"
        "Check status:\n"
        "/status @username\n\n"
        "Stop monitoring:\n"
        "/stop @username"
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
        f"🕐 Monitoring started: "
        f"{format_turkey_time(started_at)}"
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

    last_checked = (
        format_turkey_time(account[3])
        if account[3]
        else "Not checked yet"
    )

    await update.message.reply_text(
        f"👻 Username: {account[0]}\n"
        f"⏳ Status: {account[2]}\n"
        f"🕐 Monitoring started: "
        f"{format_turkey_time(account[1])}\n"
        f"🔍 Last checked: {last_checked}"
    )


async def stop_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: /stop @username"
        )
        return

    username = context.args[0].lower()

    if not username.startswith("@"):
        username = "@" + username

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE accounts
        SET status = 'stopped'
        WHERE username = ?
        """,
        (username,)
    )

    conn.commit()

    updated = cursor.rowcount

    conn.close()

    if updated:
        await update.message.reply_text(
            f"🛑 Monitoring stopped for {username}."
        )
    else:
        await update.message.reply_text(
            f"❌ No monitoring record found for {username}."
        )


async def monitor_accounts(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT username, started_at, status, notified
        FROM accounts
        WHERE status = 'monitoring'
        """
    )

    accounts = cursor.fetchall()

    for username, started_at, current_status, notified in accounts:

        result = check_instagram(username)

        now_utc = datetime.now(timezone.utc)
        now_iso = now_utc.isoformat()

        cursor.execute(
            """
            UPDATE accounts
            SET last_checked = ?
            WHERE username = ?
            """,
            (now_iso, username)
        )

        conn.commit()

        # Do nothing if Instagram returns an uncertain result
        if result == "unknown":
            continue

        # Wait until the account becomes active
        if result != "active":
            continue

        # Do not send the notification more than once
        if notified == 1:
            continue

        start_time = datetime.fromisoformat(started_at)

        elapsed_seconds = (
            now_utc - start_time
        ).total_seconds()

        monitoring_started = format_turkey_time(started_at)
        detected_at = format_turkey_time(now_iso)
        duration = format_duration(elapsed_seconds)

        message = (
            "✅ Instagram Account Is Active\n\n"
            f"👻 Username: {username}\n"
            "🟢 Status: Active\n"
            f"⏱️ Time until activation: {duration}\n"
            f"🕐 Monitoring started: {monitoring_started}\n"
            f"🔍 Detected at: {detected_at}"
        )

        chat_id = context.application.bot_data.get("chat_id")

        if chat_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text=message
            )

        cursor.execute(
            """
            UPDATE accounts
            SET status = 'active',
                notified = 1
            WHERE username = ?
            """,
            (username,)
        )

        conn.commit()

    conn.close()


async def save_chat_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    context.application.bot_data["chat_id"] = (
        update.effective_chat.id
    )

    await update.message.reply_text(
        "✅ Notification settings saved.\n"
        "You will receive automatic activation alerts here."
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
        CommandHandler("stop", stop_account)
    )

    app.add_handler(
        CommandHandler("notify", save_chat_id)
    )

    # Check monitored accounts every 5 minutes
    app.job_queue.run_repeating(
        monitor_accounts,
        interval=CHECK_INTERVAL,
        first=10
    )

    print("ISMC Bot is running...")

    app.run_polling()


if __name__ == "__main__":
    main()
