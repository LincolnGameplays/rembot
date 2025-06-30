import logging
import aiohttp

from . import config
from .services import chroma_service, db_service, learning_service

logger = logging.getLogger(__name__)

async def analyze_memory_themes(user_id: int, long_term_memories: list) -> str:
    """Uses the LLM to analyze long-term memories and identify a dominant emotional theme."""
    if not long_term_memories:
        return ""

    memory_text = "\n".join(long_term_memories)
    prompt = f"""
Analise os seguintes resumos de memória de um usuário e identifique o tema emocional dominante. Responda com uma única frase descritiva.

Exemplos de resposta:
- O Mestre parece estar focado em seus objetivos de carreira e desenvolvimento pessoal.
- O Mestre tem compartilhado muitas de suas preocupações e ansiedades recentemente.
- As conversas recentes têm sido leves, focadas em hobbies e atividades divertidas.

[Memórias para Analisar]:
{memory_text}

[Tema Emocional Dominante]:
"""

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{config.LLM_API_URL}/generate", json={
                "prompt": prompt,
                "max_tokens": 100,
                "temperature": 0.5,
            }) as response:
                response.raise_for_status()
                data = await response.json()
                theme = data["text"].strip()
                logger.info(f"Memory theme for user {user_id}: {theme}")
                return theme
    except Exception as e:
        logger.error(f"Failed to analyze memory themes for user {user_id}: {e}")
        return ""

async def generate_rem_response(context, user_id: int, user_message: str, user_data: dict, recent_conversations: list, relevant_memories: list):
    """Constructs the prompt and sends a request to the LLM API to generate a response."""
    affection = user_data['affection_level']
    trust = user_data['trust_level']
    happiness = user_data['happiness_level']
    mood = user_data['mood_state']
    current_language = user_data['current_language']

    # --- Memory Theme Analysis ---
    long_term_memories = await chroma_service.get_relevant_memories(context, user_id, "resumo da memória", n_results=5)
    memory_theme = await analyze_memory_themes(user_id, long_term_memories)

    # --- Global Learning - Best Interaction Patterns ---
    situation_label = await learning_service.classify_situation(user_message)
    best_patterns = []
    if situation_label:
        best_patterns = await db_service.get_best_interaction_patterns(context, situation_label)

    mood_description_short = {
        'neutral': 'neutra',
        'happy': 'feliz',
        'sad': 'triste',
        'joyful': 'radiante',
        'worried': 'preocupada',
        'curious': 'curiosa',
        'playful': 'brincalhona'
    }.get(mood, 'neutra')

    # Build the core personality and context
    core_prompt = config.REM_PERSONALITY_PROMPT
    core_prompt += f"\nRem está {mood_description_short} (Afeto: {affection}, Confiança: {trust}, Felicidade: {happiness})."

    if memory_theme:
        core_prompt += f"\n[Contexto de Longo Prazo]: {memory_theme}"

    if best_patterns:
        core_prompt += "\n[Exemplos de Respostas Ideais]:\n"
        for pattern in best_patterns:
            core_prompt += f"- {pattern['rem_response']}\n"

    # Add recent conversation history
    history_str = "\n".join([f"{conv['speaker']}: {conv['message_text']}" for conv in recent_conversations])
    if history_str:
        core_prompt += f"\n[Histórico Recente]:\n{history_str}"

    # Add relevant short-term memories
    if relevant_memories:
        core_prompt += f"\n[Memórias Relevantes]:\n" + "\n".join([f"- {m}" for m in relevant_memories])

    # Final instruction and user message
    prompt = f"""
{core_prompt}

[Idioma: {current_language}.]

User: {user_message}
Rem:
"""

    logger.info(f"Sending prompt to LLM API for user {user_id}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{config.LLM_API_URL}/generate", json={
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
        return config.get_message("llm_api_error", current_language)
    except Exception as e:
        logger.error(f"Unexpected error during LLM generation: {e}")
        return config.get_message("llm_unexpected_error", current_language)