import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Bot is active!\n\n"
        "To add an account:\n"
        "/add @username"
    )


async def add_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: /add @username"
        )
        return

    username = context.args[0]

    await update.message.reply_text(
        f"👑 Account Unbanned 👑\n\n"
        f"👻 Username: {username}\n"
        f"👥 Followers: Checking...\n"
        f"⏳ Time taken: Calculating...\n\n"
        f"🔗 View Profile - {username}"
    )


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_account))

    print("Bot is running...")

    app.run_polling()


if __name__ == "__main__":
    main()
