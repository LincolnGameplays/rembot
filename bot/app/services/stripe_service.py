import logging
import stripe
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from . import config
from .services import db_service

logger = logging.getLogger(__name__)

def init_stripe():
    """Initializes the Stripe API key."""
    stripe.api_key = config.STRIPE_SECRET_KEY
    logger.info("Stripe API key initialized.")

async def send_subscription_offer(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """Sends the Stripe invoice to the user."""
    lang = (await db_service.get_user(context, user_id))['current_language']

    if not config.STRIPE_PRODUCT_PRICE_ID or not config.TELEGRAM_PAYMENT_PROVIDER_TOKEN:
        logger.error("Stripe settings (price ID or provider token) are not configured.")
        await update.message.reply_text(config.get_message("stripe_generic_error", lang))
        return

    try:
        price = stripe.Price.retrieve(config.STRIPE_PRODUCT_PRICE_ID)
        product = stripe.Product.retrieve(price.product)
        title = product.name
        description = product.description
        currency = price.currency
        amount = price.unit_amount
    except stripe.error.StripeError as e:
        logger.error(f"Stripe API error while retrieving price/product: {e}", exc_info=True)
        await update.message.reply_text(config.get_message("stripe_details_error", lang))
        return

    # A placeholder image can be used
    photo_url = "https://via.placeholder.com/200x200.png?text=RemBOT"

    await context.bot.send_invoice(
        chat_id=user_id,
        title=title,
        description=description,
        payload=f"rembot_subscription_{user_id}",
        provider_token=config.TELEGRAM_PAYMENT_PROVIDER_TOKEN,
        currency=currency,
        prices=[{"label": title, "amount": amount}],
        start_parameter="rembot_subscribe",
        photo_url=photo_url,
        photo_width=200,
        photo_height=200,
        need_name=False,
        need_phone_number=False,
        need_email=False,
        need_shipping_address=False,
        is_flexible=False,
        disable_notification=False,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Assinar agora! 💖", pay=True)
        ]])
    )
    logger.info(f"Subscription offer sent to user {user_id}")

async def pre_checkout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Answers pre-checkout queries from Telegram."""
    query = update.pre_checkout_query
    user_id = query.from_user.id
    lang = (await db_service.get_user(context, user_id))['current_language']

    if query.invoice_payload.startswith("rembot_subscription_"):
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message=config.get_message("payment_pre_checkout_error", lang))

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles successful payment callbacks."""
    user_id = update.effective_user.id
    payload = update.message.successful_payment.invoice_payload
    stripe_charge_id = update.message.successful_payment.provider_payment_charge_id
    lang = (await db_service.get_user(context, user_id))['current_language']

    if payload.startswith("rembot_subscription_"):
        await db_service.update_user_subscription_status(context, user_id, "active", stripe_charge_id)
        await update.message.reply_text(config.get_message("payment_successful", lang))
        logger.info(f"User {user_id} successfully subscribed (Charge ID: {stripe_charge_id}).")
    else:
        logger.warning(f"Unknown successful payment payload: {payload}")
        await update.message.reply_text(config.get_message("payment_unknown_payload", lang))
