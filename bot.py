import os
import sqlite3
import asyncio
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

# Normal monitoring interval: 5 minutes
CHECK_INTERVAL = 300

# Confirmation interval: 1 minute
CONFIRMATION_INTERVAL = 60

# Turkey time: UTC+3
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

    return dt.strftime(
        "%B %d, %Y at %I:%M %p"
    ).replace(" 0", " ")


def format_duration(seconds):
    seconds = int(seconds)

    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60

    parts = []

    if days:
        parts.append(
            f"{days} day" if days == 1 else f"{days} days"
        )

    if hours:
        parts.append(
            f"{hours} hour" if hours == 1 else f"{hours} hours"
        )

    if minutes:
        parts.append(
            f"{minutes} minute"
            if minutes == 1
            else f"{minutes} minutes"
        )

    if not parts:
        return "Less than 1 minute"

    return ", ".join(parts)


def check_instagram(username):
    clean_username = username.replace("@", "").strip()

    url = f"https://www.instagram.com/{clean_username}/"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=20,
            allow_redirects=True
        )

        # Only HTTP 200 counts as an active candidate.
        if response.status_code == 200:
            return True

        return False

    except requests.RequestException:
        return False


def update_last_checked(username, timestamp):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE accounts
        SET last_checked = ?
        WHERE username = ?
        """,
        (timestamp, username)
    )

    conn.commit()
    conn.close()


def get_monitored_accounts():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT username, started_at, notified
        FROM accounts
        WHERE status = 'monitoring'
        """
    )

    accounts = cursor.fetchall()

    conn.close()

    return accounts


def mark_active(username):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

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


async def send_activation_notification(
    context,
    username,
    started_at,
    detected_at
):
    start_time = datetime.fromisoformat(
        started_at
    )

    detected_time = datetime.fromisoformat(
        detected_at
    )

    elapsed_seconds = (
        detected_time - start_time
    ).total_seconds()

    duration = format_duration(
        elapsed_seconds
    )

    message = (
        "✅ Instagram Account Is Active\n\n"
        f"👻 Username: {username}\n"
        "🟢 Status: Active\n"
        f"⏱️ Time until activation: {duration}\n"
        f"🕐 Monitoring started: "
        f"{format_turkey_time(started_at)}\n"
        f"🔍 Detected at: "
        f"{format_turkey_time(detected_at)}"
    )

    chat_id = context.application.bot_data.get(
        "chat_id"
    )

    if chat_id:
        await context.bot.send_message(
            chat_id=chat_id,
            text=message
        )

        mark_active(username)


async def confirm_activation(
    context,
    username,
    started_at
):
    """
    First HTTP 200 has been detected.

    Check again after 1 minute.
    If 200 again, check one more time after 1 minute.
    Only after 3 consecutive HTTP 200 responses
    is the account considered active.
    """

    # Confirmation #2
    await asyncio.sleep(
        CONFIRMATION_INTERVAL
    )

    result_2 = check_instagram(
        username
    )

    now_2 = datetime.now(
        timezone.utc
    ).isoformat()

    update_last_checked(
        username,
        now_2
    )

    if not result_2:
        return

    # Confirmation #3
    await asyncio.sleep(
        CONFIRMATION_INTERVAL
    )

    result_3 = check_instagram(
        username
    )

    now_3 = datetime.now(
        timezone.utc
    ).isoformat()

    update_last_checked(
        username,
        now_3
    )

    if not result_3:
        return

    # Three consecutive HTTP 200 responses.
    await send_activation_notification(
        context,
        username,
        started_at,
        now_3
    )


async def monitor_accounts(
    context: ContextTypes.DEFAULT_TYPE
):
    accounts = get_monitored_accounts()

    for (
        username,
        started_at,
        notified
    ) in accounts:

        if notified == 1:
            continue

        # Normal 5-minute check
        result = check_instagram(
            username
        )

        now = datetime.now(
            timezone.utc
        ).isoformat()

        update_last_checked(
            username,
            now
        )

        # If not HTTP 200, continue normal monitoring.
        if not result:
            continue

        # First 200 detected.
        # Start the 2-step, 1-minute confirmation.
        await confirm_activation(
            context,
            username,
            started_at
        )


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "🤖 ISMC Bot is active!\n\n"
        "Start monitoring:\n"
        "/add @username\n\n"
        "Check status:\n"
        "/status @username\n\n"
        "Stop monitoring:\n"
        "/stop @username\n\n"
        "Set notification chat:\n"
        "/notify"
    )


async def add_account(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not context.args:
        await update.message.reply_text(
            "Usage: /add @username"
        )
        return

    username = context.args[0].lower()

    if not username.startswith("@"):
        username = "@" + username

    started_at = datetime.now(
        timezone.utc
    ).isoformat()

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR REPLACE INTO accounts
        (
            username,
            started_at,
            status,
            last_checked,
            notified
        )
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


async def status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
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
        SELECT
            username,
            started_at,
            status,
            last_checked
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


async def stop_account(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
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
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "add",
            add_account
        )
    )

    app.add_handler(
        CommandHandler(
            "status",
            status
        )
    )

    app.add_handler(
        CommandHandler(
            "stop",
            stop_account
        )
    )

    app.add_handler(
        CommandHandler(
            "notify",
            save_chat_id
        )
    )

    # Normal monitoring every 5 minutes.
    app.job_queue.run_repeating(
        monitor_accounts,
        interval=CHECK_INTERVAL,
        first=10
    )

    print(
        "ISMC Bot is running..."
    )

    app.run_polling()


if __name__ == "__main__":
    main()
