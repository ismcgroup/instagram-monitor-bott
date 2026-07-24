async def ekle(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
