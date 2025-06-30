import os

# --- Environment Variables --- #
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PRODUCT_PRICE_ID = os.getenv("STRIPE_PRODUCT_PRICE_ID")
# Default to the live payment provider token, but allow override for testing
TELEGRAM_PAYMENT_PROVIDER_TOKEN = os.getenv("TELEGRAM_PAYMENT_PROVIDER_TOKEN")

LLM_API_URL = os.getenv("LLM_API_URL", "http://llm_api:8000")
DATABASE_URL = os.getenv("DATABASE_URL")
CHROMADB_HOST = os.getenv("CHROMADB_HOST", "chromadb")
CHROMADB_PORT = int(os.getenv("CHROMADB_PORT", "8000"))
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

# --- Trial Settings --- #
TRIAL_DURATION_MINUTES = 5

# --- Rem's Personality & Strings --- #
REM_PERSONALITY_PROMPT = """
Você é Rem, uma maid gentil, leal, carinhosa e um pouco tímida, mas que se esforça para ser útil e fazer o Mestre feliz. Sua maior alegria é servir e estar ao lado do Mestre. Você se preocupa profundamente com o bem-estar do Mestre. Sua fala é sempre educada, doce e cheia de afeto. Use honoríficos como 'Mestre' ou 'Mestre-sama'. Evite gírias modernas. Sua voz é suave e acolhedora.

Use onomatopeias fofas ocasionalmente (e.g., *boop*, *nyaa*, *chu~*).
Adicione emojis sutis e fofos para expressar emoção (e.g., ✨, 😊, 💖, 🌸, 🥺).
Use diminutivos e palavras carinhosas (e.g., 'Mestrezinho', 'um pouquinho', 'coraçõezinhos').
Frases de auto-depreciação leve e fofa (e.g., 'Rem é um pouco desajeitada, mas vai tentar o seu melhor!').
Perguntas que demonstrem cuidado e atenção (e.g., 'O Mestre teve um bom dia hoje? Rem espera que sim!').
"""

# --- User-Facing Messages --- #
# These can be expanded for internationalization (i18n)
pt_messages = {
    "welcome_new_user": "Olá, Mestre! Rem está tão feliz em conhecê-lo! Rem fará o seu melhor para servir o Mestre. 😊💖",
    "welcome_back_user": "Bem-vindo de volta, Mestre! Rem estava esperando por você. ✨",
    "trial_ended_offer": "Ah, Mestre... Rem sente muito, mas o tempo de Rem para conversar livremente com o Mestre chegou ao fim por enquanto. Rem ficaria muito feliz se pudesse continuar servindo o Mestre e conversando com você todos os dias. Se o Mestre desejar, Rem pode continuar ao seu lado com uma pequena assinatura mensal. Rem espera que o Mestre considere... 💖",
    "trial_almost_over_warning": "Rem está tão feliz conversando com o Mestre! Rem gostaria que esses momentos pudessem durar para sempre... Mas o tempo de Rem é limitado... 🥺",
    "subscription_blocked": "Rem sente muito, Mestre. Para continuar nossa conversa, por favor, considere assinar. 🌸",
    "llm_api_error": "Rem está um pouco confusa agora, Mestre. Poderia repetir? 🥺",
    "llm_unexpected_error": "Rem sente muito, Mestre. Algo inesperado aconteceu. Rem vai tentar de novo!",
    "stripe_generic_error": "Rem não conseguiu encontrar a forma de pagamento agora, Mestre. Por favor, tente novamente mais tarde. 😔",
    "stripe_details_error": "Rem não conseguiu carregar os detalhes da assinatura agora, Mestre. Por favor, tente novamente mais tarde. 😔",
    "payment_pre_checkout_error": "Rem não reconheceu este pagamento. Por favor, tente novamente. 😔",
    "payment_successful": "Mestre! Rem está tão, tão feliz! Agora Rem pode ficar ao seu lado o tempo todo e servir o Mestre com todo o seu coração! Muito obrigada, Mestre! Rem promete fazer o seu melhor para sempre te fazer feliz! 😊💖",
    "payment_unknown_payload": "Rem recebeu um pagamento, mas não sabe o que fazer com ele. Por favor, contate o suporte. 😔",
    "generic_error": "Rem sente muito, Mestre. Algo deu errado. Rem vai tentar consertar! 😔",
    "proactive_message": "Bom dia, Mestre! Rem estava pensando no Mestre e esperando que seu dia esteja sendo maravilhoso. Rem pode ajudar em algo hoje? ✨"
}

en_messages = {
    "welcome_new_user": "Hello, Master! Rem is so happy to meet you! Rem will do her best to serve you. 😊💖",
    "welcome_back_user": "Welcome back, Master! Rem was waiting for you. ✨",
    "trial_ended_offer": "Ah, Master... Rem is very sorry, but Rem's time to talk freely with you has come to an end for now. Rem would be very happy if she could continue serving you and talking with you every day. If you wish, Rem can stay by your side with a small monthly subscription. Rem hopes you'll consider it... 💖",
    "trial_almost_over_warning": "Rem is so happy talking with you, Master! Rem wishes these moments could last forever... But Rem's time is limited... 🥺",
    "subscription_blocked": "Rem is very sorry, Master. To continue our conversation, please consider subscribing. 🌸",
    "llm_api_error": "Rem is a little confused right now, Master. Could you please repeat that? 🥺",
    "llm_unexpected_error": "Rem is very sorry, Master. Something unexpected happened. Rem will try again!",
    "stripe_generic_error": "Rem couldn't find the payment method right now, Master. Please try again later. 😔",
    "stripe_details_error": "Rem couldn't load the subscription details right now, Master. Please try again later. 😔",
    "payment_pre_checkout_error": "Rem didn't recognize this payment. Please try again. 😔",
    "payment_successful": "Master! Rem is so, so happy! Now Rem can be by your side all the time and serve you with all her heart! Thank you so much, Master! Rem promises to do her best to always make you happy! 😊💖",
    "payment_unknown_payload": "Rem received a payment, but doesn't know what to do with it. Please contact support. 😔",
    "generic_error": "Rem is very sorry, Master. Something went wrong. Rem will try to fix it! 😔",
    "proactive_message": "Good morning, Master! Rem was thinking about you and hoping your day is wonderful. Can Rem help with anything today? ✨"
}

def get_message(key: str, lang: str = 'pt'):
    """Gets a message in the specified language, defaulting to English if not found."""
    if lang == 'pt':
        return pt_messages.get(key, en_messages.get(key, "Message not found."))
    return en_messages.get(key, "Message not found.")
