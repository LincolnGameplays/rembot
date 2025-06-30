import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from langdetect import detect, LangDetectException

from . import config
from .services import db_service, emotion_service, llm_service, chroma_service, learning_service

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    # Get Telegram's language code, default to 'pt' if not available
    telegram_lang_code = update.effective_user.language_code if update.effective_user.language_code else 'pt'

    user = await db_service.get_user(context, user_id)
    if not user:
        user = await db_service.create_user(context, user_id, initial_language=telegram_lang_code)
        lang = user['current_language'] # Use the language stored in DB
        await update.message.reply_text(config.get_message("welcome_new_user", lang))
    else:
        lang = user['current_language']
        await update.message.reply_text(config.get_message("welcome_back_user", lang))
    await db_service.update_user_interaction_time(context, user_id)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_message = update.message.text

    if not user_message:
        return

    await db_service.update_user_interaction_time(context, user_id)

    # Fetch user data before potential updates to detect status change
    old_user_data = await db_service.get_user(context, user_id)
    if not old_user_data:
        old_user_data = await db_service.create_user(context, user_id, initial_language=update.effective_user.language_code if update.effective_user.language_code else 'pt')

    user = await db_service.get_user(context, user_id) # Get fresh user data after potential creation

    lang = user['current_language']

    # --- Post-Subscription Experience --- #
    # Check if subscription just became active and message hasn't been sent
    if user['subscription_status'] == 'active' and not user['subscription_activated_message_sent']:
        await update.message.reply_text(config.get_message("subscription_activated_thanks", lang))
        await update.message.reply_text(config.get_message("subscription_activated_full_access", lang))
        await db_service.set_subscription_activated_message_sent(context, user_id)
        # No return here, allow the message to be processed normally after welcome

    # --- Language Detection and Update --- #
    try:
        detected_lang = detect(user_message)
        # Only update if detected language is different from stored and is a supported language
        if detected_lang != lang and detected_lang in ['pt', 'en']:
            await db_service.update_user_language(context, user_id, detected_lang)
            lang = detected_lang # Update current lang variable for this interaction
            logger.info(f"User {user_id} language updated to {detected_lang}")
    except LangDetectException:
        logger.warning(f"Could not detect language for user {user_id} message: {user_message}")

    # Update emotions based on message
    await emotion_service.update_user_emotions(context, user_id, user_message)

    # Save user message to conversation history
    user_conversation_id = await db_service.save_conversation(context, user_id, "User", user_message)

    # Check trial status
    if user['subscription_status'] == 'trial':
        time_left_seconds = (user['trial_end_time'] - datetime.now()).total_seconds()
        
        # Send trial warnings based on thresholds
        for threshold_seconds, message_key in sorted(config.TRIAL_WARNING_THRESHOLDS.items(), reverse=True):
            if time_left_seconds <= threshold_seconds and user['trial_warning_sent'] != message_key:
                await update.message.reply_text(config.get_message(message_key, lang))
                await db_service.set_trial_warning_sent(context, user_id, message_key)
                break # Send only one warning per message

        # Trial ended
        if time_left_seconds <= 0:
            await update.message.reply_text(config.get_message("trial_ended_offer", lang))
            await send_subscription_offer(update, context, user_id) # Call the new local function
            return

    # If not subscribed and trial ended, block further conversation
    if user['subscription_status'] == 'trial' and (user['trial_end_time'] - datetime.now()).total_seconds() <= 0:
        await update.message.reply_text(config.get_message("subscription_blocked", lang))
        return

    # Get context for LLM
    recent_conversations = await db_service.get_recent_conversations(context, user_id)
    relevant_memories = await chroma_service.get_relevant_memories(context, user_id, user_message)

    # Generate and send response
    rem_response = await llm_service.generate_rem_response(context, user_id, user_message, user, recent_conversations, relevant_memories)
    
    # Save Rem's response to conversation history
    rem_conversation_id = await db_service.save_conversation(context, user_id, "Rem", rem_response)

    # Create inline keyboard for feedback
    keyboard = [
        [InlineKeyboardButton("👍", callback_data=f"feedback_{rem_conversation_id}_1"),
         InlineKeyboardButton("👎", callback_data=f"feedback_{rem_conversation_id}_-1")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(rem_response, reply_markup=reply_markup)

    # Evaluate and save interaction for global learning
    await learning_service.evaluate_and_save_interaction(context, user_id, user_message, rem_response, rem_conversation_id)

async def send_subscription_offer(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """Sends a link to the AstronFy bot for subscription."""
    lang = (await db_service.get_user(context, user_id))['current_language']
    
    # Construct the deep link for the AstronFy bot
    # The 'start' parameter will be 'rembot_subscribe_[USER_ID]'
    # AstronFy bot should be configured to handle this parameter
    astronfy_link = f"https://t.me/{config.ASTRONFY_BOT_USERNAME}?start=rembot_subscribe_{user_id}"

    keyboard = [
        [InlineKeyboardButton("Assinar agora! 💖", url=astronfy_link)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        config.get_message("trial_ended_offer", lang) + "\n\n" +
        config.get_message("payment_offer_text", lang),
        reply_markup=reply_markup
    )
    logger.info(f"AstronFy subscription link sent to user {user_id}: {astronfy_link}")

async def handle_feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer() # Acknowledge the callback query

    data = query.data.split('_')
    if len(data) == 3 and data[0] == 'feedback':
        conversation_id = int(data[1])
        score = int(data[2])
        user_id = query.from_user.id

        # Record explicit feedback
        await learning_service.record_explicit_feedback(context, conversation_id, score)

        # Edit the message to remove buttons and indicate feedback received
        try:
            await query.edit_message_reply_markup(reply_markup=None) # Remove buttons
            # Optionally, add a small text indicating feedback received
            # await query.edit_message_text(text=query.message.text + "\n\n(Feedback recebido!)")
        except Exception as e:
            logger.warning(f"Could not edit message after feedback: {e}")

    else:
        logger.warning(f"Unknown callback_data: {query.data}")

async def admin_activate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    lang = (await db_service.get_user(context, user_id))['current_language']

    if user_id != config.ADMIN_TELEGRAM_ID:
        await update.message.reply_text(config.get_message("admin_not_authorized", lang))
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Mestre, por favor, use: /admin_activate <ID_do_usuario>")
        return

    target_user_id = int(context.args[0])
    
    # Update user's subscription status to 'active'
    success = await db_service.update_user_subscription_status(context, target_user_id, "active")

    if success:
        await update.message.reply_text(config.get_message("admin_activate_success", lang).format(user_id=target_user_id))
    else:
        await update.message.reply_text(config.get_message("admin_activate_fail", lang).format(user_id=target_user_id))

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Exception while handling an update: {context.error}", exc_info=True)
    if update and update.effective_message:
        try:
            user_id = update.effective_user.id
            lang = (await db_service.get_user(context, user_id))['current_language']
            await update.effective_message.reply_text(config.get_message("generic_error", lang))
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")