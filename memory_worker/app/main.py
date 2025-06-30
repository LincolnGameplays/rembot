import asyncio
import asyncpg
import os
import logging
from datetime import datetime, timedelta
from sentence_transformers import SentenceTransformer
import chromadb
import aiohttp

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
LLM_API_URL = os.getenv("LLM_API_URL", "http://llm_api:8000")
CHROMADB_HOST = os.getenv("CHROMADB_HOST", "chromadb")
CHROMADB_PORT = int(os.getenv("CHROMADB_PORT", "8000"))
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

# Global clients
db_pool = None
chroma_client = None
embedding_model = None

async def init_clients():
    global db_pool, chroma_client, embedding_model
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    chroma_client = chromadb.HttpClient(host=CHROMADB_HOST, port=CHROMADB_PORT)
    embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    logger.info("Memory worker clients initialized.")

async def get_users_for_memory_processing():
    async with db_pool.acquire() as conn:
        users = await conn.fetch(
            "SELECT telegram_id FROM users WHERE subscription_status = 'active' AND last_interaction_timestamp > NOW() - INTERVAL '48 hours'"
        )
        return [user['telegram_id'] for user in users]

async def get_conversations_for_summary(user_id: int, since_last_summary: datetime):
    async with db_pool.acquire() as conn:
        conversations = await conn.fetch(
            "SELECT speaker, message_text FROM conversations WHERE user_id = $1 AND timestamp > $2 ORDER BY timestamp ASC",
            user_id, since_last_summary
        )
        return conversations

async def generate_summary_with_llm(user_id: int, conversation_history: str):
    prompt = f"""
    You are an AI assistant tasked with summarizing conversations between a user (Mestre) and an AI maid (Rem). 
    Your goal is to extract key facts, relationship dynamics, and important topics discussed. 
    Focus on information that would be useful for Rem to remember about the Mestre for future interactions.
    Be concise and extract only the most important, actionable information.

    Conversation History:
    {conversation_history}

    Based on the conversation above, summarize the key facts and relationship points about the Mestre. 
    Format as a concise list of bullet points. Example: 
    - Mestre likes coffee.
    - Mestre had a stressful day.
    - Mestre is interested in anime.
    """
    
    logger.info(f"Generating summary for user {user_id} with LLM API.")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{LLM_API_URL}/generate", json={
                "prompt": prompt,
                "max_tokens": 300,
                "temperature": 0.5,
                "top_p": 0.9,
                "stop": []
            }) as response:
                response.raise_for_status()
                data = await response.json()
                return data["text"].strip()
    except aiohttp.ClientError as e:
        logger.error(f"Error connecting to LLM API for summary: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during LLM summary generation: {e}", exc_info=True)
        return None

async def save_long_term_memory_to_chroma(user_id: int, summary_text: str):
    try:
        collection = chroma_client.get_or_create_collection(name=f"user_{user_id}_memories")
        
        # Check if this exact summary already exists to avoid duplicates
        # This is a simple check, more robust de-duplication might be needed
        existing_docs = collection.query(query_texts=[summary_text], n_results=1)
        if existing_docs and existing_docs['documents'] and existing_docs['documents'][0] and existing_docs['documents'][0][0] == summary_text:
            logger.info(f"Exact summary already exists for user {user_id}. Skipping save.")
            return

        # Generate embedding for the summary
        embedding = embedding_model.encode(summary_text).tolist()

        collection.add(
            documents=[summary_text],
            embeddings=[embedding],
            metadatas=[{"user_id": user_id, "timestamp": datetime.now().isoformat()}],
            ids=[f"mem_{user_id}_{datetime.now().timestamp()}"]
        )
        logger.info(f"Saved long-term memory for user {user_id}: {summary_text}")
    except Exception as e:
        logger.error(f"Error saving long-term memory to ChromaDB for user {user_id}: {e}", exc_info=True)

async def process_user_memory(user_id: int):
    logger.info(f"Processing memory for user {user_id}")
    # In a real system, you'd track the last summary time per user in the DB
    # For now, we'll summarize conversations from the last 24 hours
    since_last_summary = datetime.now() - timedelta(hours=24)
    conversations = await get_conversations_for_summary(user_id, since_last_summary)

    if not conversations: 
        logger.info(f"No new conversations for user {user_id} to summarize.")
        return

    conversation_history_str = "\n".join([f"{c['speaker']}: {c['message_text']}" for c in conversations])
    
    summary = await generate_summary_with_llm(user_id, conversation_history_str)
    if summary:
        await save_long_term_memory_to_chroma(user_id, summary)

async def memory_worker_loop():
    await init_clients()
    while True:
        logger.info("Memory worker: Starting daily memory processing.")
        user_ids = await get_users_for_memory_processing()
        for user_id in user_ids:
            await process_user_memory(user_id)
        
        # Run once every 24 hours
        await asyncio.sleep(24 * 60 * 60) 

async def main():
    logger.info("Memory worker started.")
    await memory_worker_loop()

if __name__ == "__main__":
    asyncio.run(main())