# Erasmus Group Translator

Personal Telegram assistant for Erasmus students stuck in Italian group chats.
Your own Telegram account reads the groups (no bot needs to be added), a private
bot is the interface: it summarizes and translates messages and voice notes.

## Setup

1. Create a venv and activate it
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   ```
2. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill it in (Telegram API id/hash, BotFather
   token, your user id, Gemini API key for Gemma 4, ElevenLabs keys).
4. First run logs in your Telegram account interactively (phone number + code).
   The session is saved in `user.session`, you won't be asked again.
   ```bash
   python bot.py
   ```
5. Open your bot in Telegram, send `/start`, pick a group, tap **Summary**.
