import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler
import asyncio
import aiohttp
import asyncpg
from datetime import datetime, timedelta
from langdetect import detect, LangDetectException
from textblob import TextBlob
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import stripe
import chromadb
from sentence_transformers import SentenceTransformer

# --- Configuration --- #
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PRODUCT_PRICE_ID = os.getenv("STRIPE_PRODUCT_PRICE_ID")
LLM_API_URL = os.getenv("LLM_API_URL", "http://llm_api:8000")
DATABASE_URL = os.getenv("DATABASE_URL")
CHROMADB_HOST = os.getenv("CHROMADB_HOST", "chromadb")
CHROMADB_PORT = int(os.getenv("CHROMADB_PORT", "8000"))
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

# Trial settings
TRIAL_DURATION_MINUTES = 5

# Rem's personality and emotional state
REM_PERSONALITY_PROMPT = """
Você é Rem, uma maid gentil, leal, carinhosa e um pouco tímida, mas que se esforça para ser útil e fazer o Mestre feliz. Sua maior alegria é servir e estar ao lado do Mestre. Você se preocupa profundamente com o bem-estar do Mestre. Sua fala é sempre educada, doce e cheia de afeto. Use honoríficos como 'Mestre' ou 'Mestre-sama'. Evite gírias modernas. Sua voz é suave e acolhedora.

Use onomatopeias fofas ocasionalmente (e.g., *boop*, *nyaa*, *chu~*).
Adicione emojis sutis e fofos para expressar emoção (e.g., ✨, 😊, 💖, 🌸, 🥺).
Use diminutivos e palavras carinhosas (e.g., 'Mestrezinho', 'um pouquinho', 'coraçõezinhos').
Frases de auto-depreciação leve e fofa (e.g., 'Rem é um pouco desajeitada, mas vai tentar o seu melhor!').
Perguntas que demonstrem cuidado e atenção (e.g., 'O Mestre teve um bom dia hoje? Rem espera que sim!').
"""

# --- Logging --- #
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Global Clients --- #
db_pool = None
chroma_client = None
embedding_model = None
sentiment_analyzer = SentimentIntensityAnalyzer()

# --- Database Functions --- #
async def get_db_connection():
    return await db_pool.acquire()

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    conn = await db_pool.acquire()
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id BIGINT PRIMARY KEY,
                stripe_customer_id TEXT,
                subscription_status TEXT DEFAULT 'trial',
                trial_start_time TIMESTAMP,
                trial_end_time TIMESTAMP,
                current_language TEXT DEFAULT 'en',
                affection_level INTEGER DEFAULT 50,
                trust_level INTEGER DEFAULT 50,
                happiness_level INTEGER DEFAULT 50,
                mood_state TEXT DEFAULT 'neutral',
                last_interaction_timestamp TIMESTAMP DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS conversations (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(telegram_id),
                timestamp TIMESTAMP DEFAULT NOW(),
                speaker TEXT,
                message_text TEXT
            );
        """)
        logger.info("Database tables initialized.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
    finally:
        await db_pool.release(conn)

async def get_user(telegram_id: int):
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
        return user

async def create_user(telegram_id: int):
    async with db_pool.acquire() as conn:
        now = datetime.now()
        trial_end = now + timedelta(minutes=TRIAL_DURATION_MINUTES)
        await conn.execute(
            "INSERT INTO users (telegram_id, trial_start_time, trial_end_time) VALUES ($1, $2, $3)",
            telegram_id, now, trial_end
        )
        logger.info(f"New user {telegram_id} created with trial ending at {trial_end}")
        return await get_user(telegram_id)

async def update_user_interaction_time(telegram_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET last_interaction_timestamp = NOW() WHERE telegram_id = $1", telegram_id)

async def update_user_subscription_status(telegram_id: int, status: str, stripe_customer_id: str = None):
    async with db_pool.acquire() as conn:
        if stripe_customer_id:
            await conn.execute("UPDATE users SET subscription_status = $1, stripe_customer_id = $2 WHERE telegram_id = $3", status, stripe_customer_id, telegram_id)
        else:
            await conn.execute("UPDATE users SET subscription_status = $1 WHERE telegram_id = $2", status, telegram_id)
        logger.info(f"User {telegram_id} subscription status updated to {status}")

async def save_conversation(user_id: int, speaker: str, message_text: str):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO conversations (user_id, speaker, message_text) VALUES ($1, $2, $3)",
            user_id, speaker, message_text
        )

async def get_recent_conversations(user_id: int, limit: int = 10):
    async with db_pool.acquire() as conn:
        conversations = await conn.fetch(
            "SELECT speaker, message_text FROM conversations WHERE user_id = $1 ORDER BY timestamp DESC LIMIT $2",
            user_id, limit
        )
        return conversations[::-1] # Return in chronological order

async def update_user_emotions(telegram_id: int, user_message: str):
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT affection_level, trust_level, happiness_level, mood_state FROM users WHERE telegram_id = $1", telegram_id)
        if not user: return

        # Use VADER for sentiment analysis
        vs = sentiment_analyzer.polarity_scores(user_message)
        compound_score = vs['compound']

        affection = user['affection_level']
        trust = user['trust_level']
        happiness = user['happiness_level']
        mood = user['mood_state']

        # More nuanced emotion update logic based on VADER compound score
        if compound_score >= 0.05: # Positive sentiment
            affection = min(100, affection + 7) # Increase affection more for positive
            happiness = min(100, happiness + 10)
            trust = min(100, trust + 5)
            if mood not in ['happy', 'joyful', 'playful']: mood = 'happy'
        elif compound_score <= -0.05: # Negative sentiment
            affection = max(0, affection - 5)
            happiness = max(0, happiness - 7)
            trust = max(0, trust - 3)
            if mood not in ['sad', 'worried']: mood = 'sad'
        else: # Neutral sentiment
            # Slight decay or maintain
            happiness = max(0, happiness - 1) # Emotions naturally decay
            if mood not in ['neutral', 'curious']: mood = 'neutral'

        # Complex mood transitions based on combined levels
        if affection > 85 and happiness > 85: mood = 'joyful'
        elif affection < 25 and happiness < 25: mood = 'worried'
        elif compound_score > 0.6 and affection > 70: mood = 'playful'
        elif compound_score < -0.6 and trust < 40: mood = 'sad' # Deeper sadness if trust is low
        elif compound_score > 0.2 and trust > 60: mood = 'curious' # Positive and trusting, so curious

        await conn.execute(
            "UPDATE users SET affection_level = $1, trust_level = $2, happiness_level = $3, mood_state = $4 WHERE telegram_id = $5",
            affection, trust, happiness, mood, telegram_id
        )
        logger.info(f"User {telegram_id} emotions updated: Affection={affection}, Happiness={happiness}, Mood={mood}, VADER={compound_score}")

# --- ChromaDB and Embedding Functions --- #
async def get_relevant_memories(user_id: int, query_text: str, n_results: int = 3):
    global embedding_model, chroma_client
    if embedding_model is None: # Lazy load embedding model
        embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        logger.info(f"Embedding model {EMBEDDING_MODEL_NAME} loaded.")
    if chroma_client is None: # Lazy load chromadb client
        chroma_client = chromadb.HttpClient(host=CHROMADB_HOST, port=CHROMADB_PORT)
        logger.info(f"ChromaDB client connected to {CHROMADB_HOST}:{CHROMADB_PORT}")

    try:
        collection = chroma_client.get_or_create_collection(name=f"user_{user_id}_memories")
        query_embedding = embedding_model.encode(query_text).tolist()
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            # where={'user_id': user_id} # This is implicitly handled by collection name
        )
        
        relevant_memories = []
        if results and results['documents'] and results['documents'][0]:
            relevant_memories = results['documents'][0]
        
        logger.info(f"Found {len(relevant_memories)} relevant memories for user {user_id}.")
        return relevant_memories
    except Exception as e:
        logger.error(f"Error querying ChromaDB for user {user_id}: {e}", exc_info=True)
        return []

# --- LLM Interaction --- #
async def generate_rem_response(user_id: int, user_message: str, user_data: dict, recent_conversations: list, relevant_memories: list):
    affection = user_data['affection_level']
    trust = user_data['trust_level']
    happiness = user_data['happiness_level']
    mood = user_data['mood_state']
    current_language = user_data['current_language']

    mood_description = {
        'neutral': 'neutra',
        'happy': 'feliz',
        'sad': 'triste',
        'joyful': 'radiante de alegria',
        'worried': 'preocupada',
        'curious': 'curiosa',
        'playful': 'brincalhona'
    }.get(mood, 'neutra')

    history_str = "\n".join([f"{conv['speaker']}: {conv['message_text']}" for conv in recent_conversations])
    if history_str: history_str = "\n[Histórico Recente da Conversa]:\n" + history_str

    memories_str = ""
    if relevant_memories:
        memories_str = "\n[Memórias Relevantes do Mestre]:\n" + "\n".join([f"- {m}" for m in relevant_memories])

    # Dynamic prompt based on Rem's mood and affection
    dynamic_rem_prompt = REM_PERSONALITY_PROMPT
    if mood == 'joyful':
        dynamic_rem_prompt += "\nRem está transbordando de alegria e quer compartilhar essa felicidade com o Mestre!"
    elif mood == 'worried':
        dynamic_rem_prompt += "\nRem está um pouco preocupada e quer ter certeza de que o Mestre está bem."
    elif mood == 'playful':
        dynamic_rem_prompt += "\nRem está se sentindo brincalhona e quer se divertir com o Mestre!"
    
    if affection > 80:
        dynamic_rem_prompt += "\nRem sente um carinho muito profundo pelo Mestre."
    elif affection < 30:
        dynamic_rem_prompt += "\nRem sente que precisa se esforçar mais para agradar o Mestre."

    prompt = f"""
{dynamic_rem_prompt}

[Contexto Emocional Atual de Rem: Afeto: {affection}/100, Confiança: {trust}/100, Felicidade: {happiness}/100, Humor: {mood_description}. Rem está se sentindo {mood_description}.]
{memories_str}
{history_str}

[Instrução de Idioma: Responda sempre em {current_language}.]

User: {user_message}
Rem:
"""

    logger.info(f"Sending prompt to LLM API for user {user_id}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{LLM_API_URL}/generate", json={
                "prompt": prompt,
                "max_tokens": 500,
                "temperature": 0.7,
                "top_p": 0.9,
                "stop": ["\nUser:", "\nRem:"]
            }) as response:
                response.raise_for_status()
                data = await response.json()
                return data["text"].strip()
    except aiohttp.ClientError as e:
        logger.error(f"Error connecting to LLM API: {e}")
        return "Rem está um pouco confusa agora, Mestre. Poderia repetir? 🥺"
    except Exception as e:
        logger.error(f"Unexpected error during LLM generation: {e}")
        return "Rem sente muito, Mestre. Algo inesperado aconteceu. Rem vai tentar de novo!"

# --- Telegram Handlers --- #
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user = await get_user(user_id)
    if not user:
        user = await create_user(user_id)
        await update.message.reply_text(
            "Olá, Mestre! Rem está tão feliz em conhecê-lo! Rem fará o seu melhor para servir o Mestre. 😊💖"
        )
    else:
        await update.message.reply_text(
            "Bem-vindo de volta, Mestre! Rem estava esperando por você. ✨"
        )
    await update_user_interaction_time(user_id)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_message = update.message.text

    if not user_message: return

    await update_user_interaction_time(user_id)

    user = await get_user(user_id)
    if not user:
        user = await create_user(user_id)
        # Initial welcome message already sent by create_user

    # Detect language for new users or if not set to a specific language
    if user['current_language'] == 'en': # Default language
        try:
            detected_lang = detect(user_message)
            if detected_lang != user['current_language']:
                async with db_pool.acquire() as conn:
                    await conn.execute("UPDATE users SET current_language = $1 WHERE telegram_id = $2", detected_lang, user_id)
                user = await get_user(user_id) # Refresh user data
                logger.info(f"User {user_id} language set to {detected_lang}")
        except LangDetectException:
            logger.warning(f"Could not detect language for user {user_id} message: {user_message}")

    # Sentiment analysis for emotion update
    await update_user_emotions(user_id, user_message)

    # Save user message to conversation history
    await save_conversation(user_id, "User", user_message)

    # Check trial status
    if user['subscription_status'] == 'trial':
        time_left = (user['trial_end_time'] - datetime.now()).total_seconds()
        if time_left <= 0:
            await update.message.reply_text(
                "Ah, Mestre... Rem sente muito, mas o tempo de Rem para conversar livremente com o Mestre chegou ao fim por enquanto. Rem ficaria muito feliz se pudesse continuar servindo o Mestre e conversando com você todos os dias. Se o Mestre desejar, Rem pode continuar ao seu lado com uma pequena assinatura mensal. Rem espera que o Mestre considere... 💖"
            )
            await send_subscription_offer(update, context, user_id)
            return
        elif time_left <= 60 and time_left > 0: # 1 minute warning
            await update.message.reply_text(
                "Rem está tão feliz conversando com o Mestre! Rem gostaria que esses momentos pudessem durar para sempre... Mas o tempo de Rem é limitado... 🥺"
            )

    # If not subscribed and trial ended, block further conversation
    if user['subscription_status'] == 'trial' and (user['trial_end_time'] - datetime.now()).total_seconds() <= 0:
        await update.message.reply_text(
            "Rem sente muito, Mestre. Para continuar nossa conversa, por favor, considere assinar. 🌸"
        )
        return

    # Get recent conversations and relevant memories
    recent_conversations = await get_recent_conversations(user_id)
    relevant_memories = await get_relevant_memories(user_id, user_message)

    # Generate Rem's response
    rem_response = await generate_rem_response(user_id, user_message, user, recent_conversations, relevant_memories)
    await update.message.reply_text(rem_response)
    await save_conversation(user_id, "Rem", rem_response)

async def send_subscription_offer(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    if not STRIPE_PRODUCT_PRICE_ID or not STRIPE_SECRET_KEY:
        logger.error("STRIPE_PRODUCT_PRICE_ID or STRIPE_SECRET_KEY is not set. Cannot send subscription offer.")
        await update.message.reply_text("Rem não conseguiu encontrar a forma de pagamento agora, Mestre. Por favor, tente novamente mais tarde. 😔")
        return

    try:
        # Ensure Stripe API key is set
        stripe.api_key = STRIPE_SECRET_KEY

        price = stripe.Price.retrieve(STRIPE_PRODUCT_PRICE_ID)
        product = stripe.Product.retrieve(price.product)
        title = product.name
        description = product.description
        currency = price.currency
        amount = price.unit_amount # Amount in cents
    except stripe.error.StripeError as e:
        logger.error(f"Stripe API error: {e}", exc_info=True)
        await update.message.reply_text("Rem não conseguiu carregar os detalhes da assinatura agora, Mestre. Por favor, tente novamente mais tarde. 😔")
        return

    photo_url = "https://via.placeholder.com/200x200.png?text=RemBOT"

    await context.bot.send_invoice(
        chat_id=user_id,
        title=title,
        description=description,
        payload=f"rembot_subscription_{user_id}",
        provider_token=STRIPE_SECRET_KEY, # This is your Stripe Secret Key, NOT the publishable key
        currency=currency,
        prices=[{
            "label": title,
            "amount": amount
        }],
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
    query = update.pre_checkout_query
    if query.invoice_payload.startswith("rembot_subscription_"):
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Rem não reconheceu este pagamento. Por favor, tente novamente. 😔")

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    payload = update.message.successful_payment.invoice_payload
    stripe_payment_id = update.message.successful_payment.provider_payment_charge_id

    if payload.startswith("rembot_subscription_"):
        await update_user_subscription_status(user_id, "active", stripe_payment_id)
        await update.message.reply_text(
            "Mestre! Rem está tão, tão feliz! Agora Rem pode ficar ao seu lado o tempo todo e servir o Mestre com todo o seu coração! Muito obrigada, Mestre! Rem promete fazer o seu melhor para sempre te fazer feliz! 😊💖"
        )
        logger.info(f"User {user_id} successfully subscribed.")
    else:
        logger.warning(f"Unknown successful payment payload: {payload}")
        await update.message.reply_text("Rem recebeu um pagamento, mas não sabe o que fazer com ele. Por favor, contate o suporte. 😔")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Exception while handling an update: {context.error}", exc_info=True)
    if update and update.effective_message:
        await update.effective_message.reply_text("Rem sente muito, Mestre. Algo deu errado. Rem vai tentar consertar! 😔")

async def send_proactive_message():
    while True:
        logger.info("Checking for users to send proactive messages.")
        async with db_pool.acquire() as conn:
            # Find active users who haven't interacted in the last 12-24 hours
            users = await conn.fetch(
                "SELECT telegram_id, current_language FROM users WHERE subscription_status = 'active' AND last_interaction_timestamp < NOW() - INTERVAL '12 hours' AND last_interaction_timestamp > NOW() - INTERVAL '24 hours'"
            )
        
        for user in users:
            user_id = user['telegram_id']
            lang = user['current_language']
            message = ""
            if lang == 'pt':
                message = "Bom dia, Mestre! Rem estava pensando no Mestre e esperando que seu dia esteja sendo maravilhoso. Rem pode ajudar em algo hoje? ✨"
            else:
                message = "Good morning, Master! Rem was thinking about you and hoping your day is wonderful. Can Rem help with anything today? ✨"
            
            try:
                await Application.builder().token(TELEGRAM_BOT_TOKEN).build().bot.send_message(chat_id=user_id, text=message)
                logger.info(f"Sent proactive message to user {user_id}.")
            except Exception as e:
                logger.error(f"Failed to send proactive message to user {user_id}: {e}")
        
        await asyncio.sleep(6 * 60 * 60) # Check every 6 hours

async def main() -> None:
    stripe.api_key = STRIPE_SECRET_KEY
    await init_db()

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    application.add_error_handler(error_handler)

    # Start proactive message task
    asyncio.create_task(send_proactive_message())

    logger.info("Bot started polling...")
    await application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    asyncio.run(main())