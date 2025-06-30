import logging
import chromadb
from sentence_transformers import SentenceTransformer

from . import config

logger = logging.getLogger(__name__)

def init_chroma(app):
    """Initializes ChromaDB client and embedding model, storing them in the application context."""
    try:
        app.bot_data['chroma_client'] = chromadb.HttpClient(host=config.CHROMADB_HOST, port=config.CHROMADB_PORT)
        logger.info(f"ChromaDB client connected to {config.CHROMADB_HOST}:{config.CHROMADB_PORT}")
        # Lazy load embedding model only when first needed to save memory
        app.bot_data['embedding_model'] = None
    except Exception as e:
        logger.error(f"Error connecting to ChromaDB: {e}", exc_info=True)
        raise

def get_embedding_model(context):
    """Lazily loads and returns the embedding model."""
    if context.bot_data.get('embedding_model') is None:
        logger.info(f"Loading embedding model: {config.EMBEDDING_MODEL_NAME}")
        context.bot_data['embedding_model'] = SentenceTransformer(config.EMBEDDING_MODEL_NAME)
        logger.info("Embedding model loaded.")
    return context.bot_data['embedding_model']

async def get_relevant_memories(context, user_id: int, query_text: str, n_results: int = 3):
    """Queries ChromaDB for memories relevant to the user's query."""
    chroma_client = context.bot_data['chroma_client']
    embedding_model = get_embedding_model(context)

    try:
        collection = chroma_client.get_or_create_collection(name=f"user_{user_id}_memories")
        query_embedding = embedding_model.encode(query_text).tolist()
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
        )
        
        relevant_memories = []
        if results and results['documents'] and results['documents'][0]:
            relevant_memories = results['documents'][0]
        
        logger.info(f"Found {len(relevant_memories)} relevant memories for user {user_id}.")
        return relevant_memories
    except Exception as e:
        logger.error(f"Error querying ChromaDB for user {user_id}: {e}", exc_info=True)
        return []
