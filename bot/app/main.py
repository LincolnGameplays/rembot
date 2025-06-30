import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, PreCheckoutQueryHandler, CallbackQueryHandler

from app import config, handlers
from app.services import db_service, chroma_service, stripe_service

# --- Logging Setup --- #
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def proactive_message_task(app: Application):
    """A background task to send proactive messages to re-engage users."""
    while True:
        await asyncio.sleep(6 * 60 * 60) # Check every 6 hours
        logger.info("Running proactive message task...")
        try:
            users = await db_service.get_users_for_proactive_message(app)
            for user in users:
                user_id = user['telegram_id']
                lang = user['current_language']
                message = config.get_message("proactive_message", lang)
                try:
                    await app.bot.send_message(chat_id=user_id, text=message)
                    logger.info(f"Sent proactive message to user {user_id}.")
                except Exception as e:
                    logger.error(f"Failed to send proactive message to user {user_id}: {e}")
        except Exception as e:
            logger.error(f"Error in proactive message task: {e}", exc_info=True)

async def post_init(app: Application):
    """Initializes all services after the application has started."""
    await db_service.init_db(app)
    chroma_service.init_chroma(app)
    stripe_service.init_stripe()
    # Start the background task
    app.create_task(proactive_message_task(app))
    logger.info("All services initialized and background task started.")

async def on_shutdown(app: Application):
    """Handles graceful shutdown of services."""
    logger.info("Bot is shutting down...")
    if 'db_pool' in app.bot_data:
        await app.bot_data['db_pool'].close()
        logger.info("Database connection pool closed.")

def main() -> None:
    """Starts the bot."""
    if not config.TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN is not set. Bot cannot start.")
        return

    application = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .on_shutdown(on_shutdown)
        .build()
    )

    # Register handlers
    application.add_handler(CommandHandler("start", handlers.start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message))
    application.add_handler(PreCheckoutQueryHandler(stripe_service.pre_checkout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, stripe_service.successful_payment_callback))
    application.add_handler(CallbackQueryHandler(handlers.handle_feedback_callback, pattern=r'^feedback_'))
    application.add_error_handler(handlers.error_handler)

    logger.info("Bot polling started...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
