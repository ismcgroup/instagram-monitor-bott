import os
import sqlite3
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

TOKEN = os.getenv("BOT_TOKEN")
DB_FILE = "accounts.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            username TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


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
        (username, started_at, status)
        VALUES (?, ?, ?)
        """,
        (username, started_at, "monitoring")
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
        "SELECT username, started_at, status FROM accounts WHERE username = ?",
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
        f"🕐 Started: {account[1]}"
    )


def main():
    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_account))
    app.add_handler(CommandHandler("status", status))

    print("Bot is running...")

    app.run_polling()


if __name__ == "__main__":
    main()
