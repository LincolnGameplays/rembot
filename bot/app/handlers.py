import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from langdetect import detect, LangDetectException

from . import config
from .services import db_service, emotion_service, llm_service, chroma_service, stripe_service, learning_service

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user = await db_service.get_user(context, user_id)
    lang = 'pt' # Default to Portuguese for new users
    if not user:
        user = await db_service.create_user(context, user_id)
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

    user = await db_service.get_user(context, user_id)
    if not user:
        user = await db_service.create_user(context, user_id)

    lang = user['current_language']

    # Detect language if it's the default 'en' and update it
    if lang == 'en':
        try:
            detected_lang = detect(user_message)
            if detected_lang != 'en':
                lang = detected_lang
                pool = context.bot_data['db_pool']
                async with pool.acquire() as conn:
                    await conn.execute("UPDATE users SET current_language = $1 WHERE telegram_id = $2", lang, user_id)
                user = await db_service.get_user(context, user_id) # Refresh user data
                logger.info(f"User {user_id} language auto-set to {lang}")
        except LangDetectException:
            logger.warning(f"Could not detect language for user {user_id} message: {user_message}")

    # Update emotions based on message
    await emotion_service.update_user_emotions(context, user_id, user_message)

    # Save user message to conversation history
    user_conversation_id = await db_service.save_conversation(context, user_id, "User", user_message)

    # Check trial status
    if user['subscription_status'] == 'trial':
        time_left = (user['trial_end_time'] - datetime.now()).total_seconds()
        if time_left <= 0:
            await update.message.reply_text(config.get_message("trial_ended_offer", lang))
            await stripe_service.send_subscription_offer(update, context, user_id)
            return
        elif time_left <= 60 and not user['trial_warning_sent']:
            await update.message.reply_text(config.get_message("trial_almost_over_warning", lang))
            await db_service.set_trial_warning_sent(context, user_id)

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

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Exception while handling an update: {context.error}", exc_info=True)
    if update and update.effective_message:
        try:
            user_id = update.effective_user.id
            lang = (await db_service.get_user(context, user_id))['current_language']
            await update.effective_message.reply_text(config.get_message("generic_error", lang))
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")