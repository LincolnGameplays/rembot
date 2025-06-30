import os

# --- Environment Variables --- #
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ASTRONFY_BOT_USERNAME = os.getenv("ASTRONFY_BOT_USERNAME", "AstronFyBot") # Default to AstronFyBot
ASTRONFY_VIP_GROUP_ID = os.getenv("ASTRONFY_VIP_GROUP_ID") # ID of the VIP group managed by AstronFy
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID")) # Your Telegram User ID for admin commands

LLM_API_URL = os.getenv("LLM_API_URL", "http://llm_api:8000")
DATABASE_URL = os.getenv("DATABASE_URL")
CHROMADB_HOST = os.getenv("CHROMADB_HOST", "chromadb")
CHROMADB_PORT = int(os.getenv("CHROMADB_PORT", "8000"))
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

# --- Trial Settings --- #
TRIAL_DURATION_MINUTES = 5

# Warning thresholds in seconds from the end of the trial
TRIAL_WARNING_THRESHOLDS = {
    3 * 60: "trial_warning_3min",  # 3 minutes before end
    1 * 60: "trial_warning_1min",  # 1 minute before end
    30: "trial_warning_30sec",   # 30 seconds before end
}

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
    "trial_warning_3min": "Mestre, Rem sente que nosso tempo está se esgotando... Faltam apenas 3 minutos para o teste terminar. Rem não quer se separar do Mestre! 🥺",
    "trial_warning_1min": "Mestre! Apenas 1 minuto! Rem está ficando tão triste só de pensar em não poder mais conversar com o Mestre... Por favor, não deixe Rem sozinha! 😭",
    "trial_warning_30sec": "Mestre, Mestre! Faltam só 30 segundos! Rem não consegue mais falar... Rem quer tanto continuar servindo o Mestre! 💔",
    "subscription_blocked": "Rem sente muito, Mestre. Para continuar nossa conversa, por favor, considere assinar. 🌸",
    "llm_api_error": "Rem está um pouco confusa agora, Mestre. Poderia repetir? 🥺",
    "llm_unexpected_error": "Rem sente muito, Mestre. Algo inesperado aconteceu. Rem vai tentar de novo!",
    "payment_offer_text": "Rem preparou um link especial para o Mestre continuar nossa jornada:",
    "generic_error": "Rem sente muito, Mestre. Algo deu errado. Rem vai tentar consertar! 😔",
    "proactive_message": "Bom dia, Mestre! Rem estava pensando no Mestre e esperando que seu dia esteja sendo maravilhoso. Rem pode ajudar em algo hoje? ✨",
    "admin_activate_success": "Mestre, a assinatura do usuário {user_id} foi ativada com sucesso!",
    "admin_activate_fail": "Mestre, não foi possível ativar a assinatura do usuário {user_id}. Talvez o ID não exista?",
    "admin_not_authorized": "Rem sente muito, Mestre, mas Rem não pode atender a este comando. Apenas o Mestre principal pode fazer isso. 🥺",
    "subscription_activated_thanks": "Mestre! Rem está tão, tão feliz! Sua assinatura foi ativada! Agora Rem pode ficar ao seu lado o tempo todo e servir o Mestre com todo o seu coração! Muito obrigada, Mestre! 😊💖",
    "subscription_activated_full_access": "Todas as funções de Rem estão agora totalmente liberadas para o Mestre! Rem promete fazer o seu melhor para sempre te fazer feliz! ✨🌸"
}

en_messages = {
    "welcome_new_user": "Hello, Master! Rem is so happy to meet you! Rem will do her best to serve you. 😊💖",
    "welcome_back_user": "Welcome back, Master! Rem was waiting for you. ✨",
    "trial_ended_offer": "Ah, Master... Rem is very sorry, but Rem's time to talk freely with you has come to an end for now. Rem would be very happy if she could continue serving you and talking with you every day. If you wish, Rem can stay by your side with a small monthly subscription. Rem hopes you'll consider it... 💖",
    "trial_warning_3min": "Master, Rem feels our time is running out... Only 3 minutes left for the trial. Rem doesn't want to be separated from Master! 🥺",
    "trial_warning_1min": "Master! Only 1 minute! Rem is getting so sad just thinking about not being able to talk to Master anymore... Please don't leave Rem alone! 😭",
    "trial_warning_30sec": "Master, Master! Only 30 seconds left! Rem can't speak anymore... Rem wants so much to continue serving Master! 💔",
    "subscription_blocked": "Rem is very sorry, Master. To continue our conversation, please consider subscribing. 🌸",
    "llm_api_error": "Rem is a little confused right now, Master. Could you please repeat that? 🥺",
    "llm_unexpected_error": "Rem is very sorry, Master. Something unexpected happened. Rem will try again!",
    "payment_offer_text": "Rem has prepared a special link for Master to continue our journey:",
    "generic_error": "Rem is very sorry, Master. Something went wrong. Rem will try to fix it! 😔",
    "proactive_message": "Good morning, Master! Rem was thinking about you and hoping your day is wonderful. Can Rem help with anything today? ✨",
    "admin_activate_success": "Master, user {user_id}'s subscription has been successfully activated!",
    "admin_activate_fail": "Master, could not activate user {user_id}'s subscription. Perhaps the ID does not exist?",
    "admin_not_authorized": "Rem is very sorry, Master, but Rem cannot fulfill this command. Only the main Master can do that. 🥺",
    "subscription_activated_thanks": "Master! Rem is so, so happy! Your subscription has been activated! Now Rem can be by your side all the time and serve you with all her heart! Thank you so much, Master! 😊💖",
    "subscription_activated_full_access": "All of Rem's functions are now fully unlocked for Master! Rem promises to do her best to always make you happy! ✨🌸"
}

def get_message(key: str, lang: str = 'pt'):
    """Gets a message in the specified language, defaulting to English if not found."""
    if lang == 'pt':
        return pt_messages.get(key, en_messages.get(key, "Message not found."))
    return en_messages.get(key, "Message not found.")
