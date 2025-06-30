import logging
from datetime import datetime, timedelta
import asyncpg

from . import config

logger = logging.getLogger(__name__)

async def init_db(app):
    """Initializes the database pool and stores it in the application context."""
    try:
        pool = await asyncpg.create_pool(config.DATABASE_URL)
        app.bot_data['db_pool'] = pool
        conn = await pool.acquire()
        try:
            # Add trial_warning_sent column
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_warning_sent BOOLEAN DEFAULT FALSE")
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_summarized_timestamp TIMESTAMP DEFAULT NOW()")

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
                    last_interaction_timestamp TIMESTAMP DEFAULT NOW(),
                    trial_warning_sent BOOLEAN DEFAULT FALSE,
                    last_summarized_timestamp TIMESTAMP DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(telegram_id),
                    timestamp TIMESTAMP DEFAULT NOW(),
                    speaker TEXT,
                    message_text TEXT
                );
                CREATE TABLE IF NOT EXISTS interaction_patterns (
                    id SERIAL PRIMARY KEY,
                    situation_label TEXT NOT NULL,
                    rem_response TEXT NOT NULL,
                    effectiveness_score REAL NOT NULL,
                    timestamp TIMESTAMP DEFAULT NOW()
                );
            """)
            logger.info("Database tables initialized and schema updated.")
        except asyncpg.PostgresError as e:
            logger.error(f"Error initializing database tables: {e}")
            raise
        finally:
            await pool.release(conn)
    except Exception as e:
        logger.error(f"Error creating database connection pool: {e}")
        raise

async def get_user(context, telegram_id: int):
    pool = context.bot_data['db_pool']
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)

async def create_user(context, telegram_id: int):
    pool = context.bot_data['db_pool']
    async with pool.acquire() as conn:
        now = datetime.now()
        trial_end = now + timedelta(minutes=config.TRIAL_DURATION_MINUTES)
        await conn.execute(
            "INSERT INTO users (telegram_id, trial_start_time, trial_end_time) VALUES ($1, $2, $3)",
            telegram_id, now, trial_end
        )
        logger.info(f"New user {telegram_id} created with trial ending at {trial_end}")
        return await get_user(context, telegram_id)

async def update_user_interaction_time(context, telegram_id: int):
    pool = context.bot_data['db_pool']
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET last_interaction_timestamp = NOW() WHERE telegram_id = $1", telegram_id)

async def update_user_subscription_status(context, telegram_id: int, status: str, stripe_customer_id: str = None):
    pool = context.bot_data['db_pool']
    async with pool.acquire() as conn:
        if stripe_customer_id:
            await conn.execute("UPDATE users SET subscription_status = $1, stripe_customer_id = $2 WHERE telegram_id = $3", status, stripe_customer_id, telegram_id)
        else:
            await conn.execute("UPDATE users SET subscription_status = $1 WHERE telegram_id = $2", status, telegram_id)
        logger.info(f"User {telegram_id} subscription status updated to {status}")

async def save_conversation(context, user_id: int, speaker: str, message_text: str):
    pool = context.bot_data['db_pool']
    # Sanitize message to prevent prompt injection issues
    sanitized_message = message_text.replace('\n', ' ').strip()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "INSERT INTO conversations (user_id, speaker, message_text) VALUES ($1, $2, $3) RETURNING id",
            user_id, speaker, sanitized_message
        )
        return result['id']

async def get_recent_conversations(context, user_id: int, limit: int = 10):
    pool = context.bot_data['db_pool']
    async with pool.acquire() as conn:
        conversations = await conn.fetch(
            "SELECT speaker, message_text FROM conversations WHERE user_id = $1 ORDER BY timestamp DESC LIMIT $2",
            user_id, limit
        )
        return conversations[::-1] # Return in chronological order

async def set_trial_warning_sent(context, telegram_id: int):
    pool = context.bot_data['db_pool']
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET trial_warning_sent = TRUE WHERE telegram_id = $1", telegram_id)

async def get_users_for_proactive_message(context):
    pool = context.bot_data['db_pool']
    async with pool.acquire() as conn:
        return await conn.fetch(
            """SELECT telegram_id, current_language FROM users 
               WHERE subscription_status = 'active' 
               AND last_interaction_timestamp BETWEEN NOW() - INTERVAL '24 hours' AND NOW() - INTERVAL '12 hours'"""
        )

async def get_users_to_summarize(pool):
    async with pool.acquire() as conn:
        return await conn.fetch(
            """SELECT telegram_id, last_summarized_timestamp FROM users
               WHERE last_interaction_timestamp > last_summarized_timestamp + INTERVAL '12 hours'"""
        )

async def get_conversations_for_summary(pool, user_id: int, since_timestamp: datetime):
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT speaker, message_text FROM conversations WHERE user_id = $1 AND timestamp > $2 ORDER BY timestamp ASC",
            user_id, since_timestamp
        )

async def update_user_summary_timestamp(pool, user_id: int):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET last_summarized_timestamp = NOW() WHERE telegram_id = $1", user_id)

async def save_interaction_pattern(context, conversation_id: int, situation_label: str, rem_response: str, effectiveness_score: float):
    pool = context.bot_data['db_pool']
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO interaction_patterns (conversation_id, situation_label, rem_response, effectiveness_score) VALUES ($1, $2, $3, $4)",
            conversation_id, situation_label, rem_response, effectiveness_score
        )

async def update_interaction_pattern_effectiveness(context, conversation_id: int, new_score: float):
    pool = context.bot_data['db_pool']
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE interaction_patterns SET effectiveness_score = $1 WHERE conversation_id = $2",
            new_score, conversation_id
        )

async def get_best_interaction_patterns(context, situation_label: str, limit: int = 3):
    pool = context.bot_data['db_pool']
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT rem_response FROM interaction_patterns WHERE situation_label = $1 ORDER BY effectiveness_score DESC LIMIT $2",
            situation_label, limit
        )
