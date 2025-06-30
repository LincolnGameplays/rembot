import logging
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from .services import db_service

logger = logging.getLogger(__name__)
sentiment_analyzer = SentimentIntensityAnalyzer()

async def update_user_emotions(context, telegram_id: int, user_message: str):
    """Analyzes user message sentiment and updates Rem's emotional state towards the user."""
    user = await db_service.get_user(context, telegram_id)
    if not user:
        return

    # Use VADER for sentiment analysis
    vs = sentiment_analyzer.polarity_scores(user_message)
    compound_score = vs['compound']

    affection = user['affection_level']
    trust = user['trust_level']
    happiness = user['happiness_level']
    mood = user['mood_state']

    # More nuanced emotion update logic based on VADER compound score
    if compound_score >= 0.05:  # Positive sentiment
        affection = min(100, affection + 7)
        happiness = min(100, happiness + 10)
        trust = min(100, trust + 5)
        if mood not in ['happy', 'joyful', 'playful']: mood = 'happy'
    elif compound_score <= -0.05:  # Negative sentiment
        affection = max(0, affection - 5)
        happiness = max(0, happiness - 7)
        trust = max(0, trust - 3)
        if mood not in ['sad', 'worried']: mood = 'sad'
    else:  # Neutral sentiment
        happiness = max(0, happiness - 1)  # Emotions naturally decay
        if mood not in ['neutral', 'curious']: mood = 'neutral'

    # Complex mood transitions based on combined levels
    if affection > 85 and happiness > 85: mood = 'joyful'
    elif affection < 25 and happiness < 25: mood = 'worried'
    elif compound_score > 0.6 and affection > 70: mood = 'playful'
    elif compound_score < -0.6 and trust < 40: mood = 'sad'
    elif compound_score > 0.2 and trust > 60: mood = 'curious'

    pool = context.bot_data['db_pool']
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET affection_level = $1, trust_level = $2, happiness_level = $3, mood_state = $4 WHERE telegram_id = $5",
            affection, trust, happiness, mood, telegram_id
        )
    logger.info(f"User {telegram_id} emotions updated: Affection={affection}, Happiness={happiness}, Mood={mood}, VADER={compound_score}")
