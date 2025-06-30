import os
import logging
import asyncio
import asyncpg
import aiohttp
import chromadb
from sentence_transformers import SentenceTransformer

# --- Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL")
LLM_API_URL = os.getenv("LLM_API_URL")
CHROMADB_HOST = os.getenv("CHROMADB_HOST", "chromadb")
CHROMADB_PORT = int(os.getenv("CHROMADB_PORT", "8000"))
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
SUMMARIZER_INTERVAL_HOURS = 6 # How often to run the summarizer

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Database Functions (specific to this worker) ---
async def get_users_to_summarize(pool):
    async with pool.acquire() as conn:
        # Find users who have interacted since their last summary
        return await conn.fetch(
            """SELECT telegram_id, last_summarized_timestamp FROM users
               WHERE last_interaction_timestamp > last_summarized_timestamp + INTERVAL '1 hour'"""
        )

async def get_conversations_for_summary(pool, user_id: int, since_timestamp):
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT speaker, message_text FROM conversations WHERE user_id = $1 AND timestamp > $2 ORDER BY timestamp ASC",
            user_id, since_timestamp
        )

async def update_user_summary_timestamp(pool, user_id: int):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET last_summarized_timestamp = NOW() WHERE telegram_id = $1", user_id)

# --- LLM Interaction ---
async def generate_summary(user_id: int, conversation_history: str):
    prompt = f"""
Crie um resumo conciso e impessoal do histórico de conversa. Foque em fatos, eventos e sentimentos importantes.

Histórico:
{conversation_history}

Resumo:
"""
    logger.info(f"Generating summary for user {user_id}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{LLM_API_URL}/generate", json={
                "prompt": prompt,
                "max_tokens": 250, # Shorter summaries
                "temperature": 0.3, # More factual
                "stop": ["\n\n"]
            }) as response:
                response.raise_for_status()
                data = await response.json()
                return data["text"].strip()
    except aiohttp.ClientError as e:
        logger.error(f"LLM API error for user {user_id}: {e}")
        return None

# --- ChromaDB Interaction ---
def save_summary_to_memory(chroma_client, embedding_model, user_id: int, summary: str):
    try:
        collection = chroma_client.get_or_create_collection(name=f"user_{user_id}_memories")
        summary_embedding = embedding_model.encode(summary).tolist()
        # Use a unique ID for the summary to prevent duplicates
        summary_id = f"summary_{int(asyncio.get_event_loop().time())}"
        
        collection.add(
            embeddings=[summary_embedding],
            documents=[summary],
            ids=[summary_id]
        )
        logger.info(f"Saved summary to ChromaDB for user {user_id}")
    except Exception as e:
        logger.error(f"ChromaDB error for user {user_id}: {e}", exc_info=True)

# --- Main Worker Loop ---
async def main():
    logger.info("Starting Memory Summarizer Worker...")
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    chroma_client = chromadb.HttpClient(host=CHROMADB_HOST, port=CHROMADB_PORT)
    embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    logger.info("Services connected.")

    while True:
        logger.info("Checking for users to summarize...")
        try:
            users_to_summarize = await get_users_to_summarize(db_pool)
            logger.info(f"Found {len(users_to_summarize)} user(s) needing summarization.")

            for user in users_to_summarize:
                user_id = user['telegram_id']
                last_summary_time = user['last_summarized_timestamp']
                
                conversations = await get_conversations_for_summary(db_pool, user_id, last_summary_time)
                if not conversations or len(conversations) < 4: # Don't summarize very short chats
                    await update_user_summary_timestamp(db_pool, user_id) # Update timestamp to avoid re-checking
                    continue

                history_str = "\n".join([f"{c['speaker']}: {c['message_text']}" for c in conversations])
                
                summary = await generate_summary(user_id, history_str)
                
                if summary:
                    save_summary_to_memory(chroma_client, embedding_model, user_id, summary)
                
                # Update the timestamp regardless of whether the summary was successful
                # to prevent getting stuck on a user with problematic conversations.
                await update_user_summary_timestamp(db_pool, user_id)

        except Exception as e:
            logger.error(f"An error occurred in the main loop: {e}", exc_info=True)
        
        logger.info(f"Sleeping for {SUMMARIZER_INTERVAL_HOURS} hours...")
        await asyncio.sleep(SUMMARIZER_INTERVAL_HOURS * 60 * 60)

if __name__ == "__main__":
    asyncio.run(main())