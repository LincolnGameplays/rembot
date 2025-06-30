import logging
import aiohttp
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from . import config
from .services import db_service

logger = logging.getLogger(__name__)
sentiment_analyzer = SentimentIntensityAnalyzer()

async def classify_situation(user_message: str) -> str:
    """Uses LLM to classify the user's message into a generic, anonymous situation label."""
    prompt = f"""
Classifique a seguinte mensagem do usuário em uma etiqueta de situação genérica e concisa. A etiqueta deve ser impessoal e não conter informações específicas do usuário. Foque no tipo de interação ou no tema geral.

Exemplos:
- Mensagem: "Eu tive um dia terrível no trabalho, meu chefe gritou comigo."
- Etiqueta: "Expressando frustração com o trabalho."

- Mensagem: "Consegui o emprego dos meus sonhos! Estou tão feliz!"
- Etiqueta: "Compartilhando uma grande conquista pessoal."

- Mensagem: "O que você acha do clima hoje?"
- Etiqueta: "Fazendo uma pergunta casual sobre o tempo."

- Mensagem: "Estou me sentindo um pouco sozinho hoje."
- Etiqueta: "Expressando sentimentos de solidão."

- Mensagem: "Você pode me contar uma piada?"
- Etiqueta: "Solicitando entretenimento."

- Mensagem: "Obrigado por me ouvir, Rem."
- Etiqueta: "Expressando gratidão."

Mensagem do Usuário: "{user_message}"
Etiqueta da Situação:
"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{config.LLM_API_URL}/generate", json={
                "prompt": prompt,
                "max_tokens": 50,
                "temperature": 0.1, # Keep it factual
                "stop": ["\n"]
            }) as response:
                response.raise_for_status()
                data = await response.json()
                label = data["text"].strip()
                logger.info(f"Classified user message '{user_message[:30]}...' as '{label}'")
                return label
    except Exception as e:
        logger.error(f"Error classifying situation: {e}")
        return "" # Return empty string if classification fails

async def evaluate_and_save_interaction(context, user_id: int, user_message: str, rem_response: str, rem_conversation_id: int):
    """Evaluates the effectiveness of Rem's response and saves the interaction pattern."""
    # 1. Classify the situation
    situation_label = await classify_situation(user_message)
    if not situation_label:
        logger.warning(f"Could not classify situation for user {user_id}. Skipping saving interaction pattern.")
        return

    # Initial effectiveness score (can be refined by explicit feedback later)
    # For now, we use the sentiment of the user's message that *triggered* Rem's response.
    vs = sentiment_analyzer.polarity_scores(user_message)
    initial_effectiveness_score = vs['compound'] # Compound score from VADER

    # 3. Save the pattern with the conversation_id
    await db_service.save_interaction_pattern(context, rem_conversation_id, situation_label, rem_response, initial_effectiveness_score)
    logger.info(f"Saved interaction pattern: '{situation_label}' -> '{rem_response[:30]}...' (Initial Score: {initial_effectiveness_score})")

async def record_explicit_feedback(context, conversation_id: int, score: int):
    """Records explicit feedback from the user and updates the effectiveness score."""
    # Convert score to a float between -1.0 and 1.0
    # Assuming score is 1 for like, -1 for dislike
    normalized_score = float(score)
    await db_service.update_interaction_pattern_effectiveness(context, conversation_id, normalized_score)
    logger.info(f"Explicit feedback recorded for conversation {conversation_id}: Score {normalized_score}")
