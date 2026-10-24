# Erasmus Group Translator

A personal Telegram assistant that lets an Erasmus student follow Italian group chats,
voice messages included, without adding any bot to the group.
Built in a 4-hour hackathon on **Gemma 4** (Gemini API) and **ElevenLabs** (TTS + Scribe STT).

Architecture and diagrams: [architecture.md](architecture.md).

## Problem

Erasmus students get added to the Telegram groups of their school, course or dorm.
Everyone writes in Italian, fast and in slang.

- Text messages have to be copied one by one into a translator. With 50+ messages a day nobody does it,
  so deadlines, room changes and decisions get missed.
- **Voice messages are the worst**: fast spoken Italian, no way to copy them, no way to translate them.
- The student is not an admin, so adding a translation bot to the group is not an option.
  Asking the Italian students to "please add this bot" is awkward and usually ignored.

## Idea

Instead of putting a bot *in* the group, give the student a **personal assistant that reads the groups
through their own Telegram account** and talks to them in private.

The student's account is already a member of every group, so it can read the history and download
voice notes. Nothing changes for the other members: no bot joins, nobody gets notified.

## Proposal

A private Telegram bot with four actions, all in the student's language:

| Action | What the student gets |
|---|---|
| **📝 Summary** | A short spoken-style briefing of the last N messages: what is urgent, events, decisions, open questions, plus a final `Deadlines:` line. Delivered as text **and as a voice note**. |
| **🌐 Translate** | The last N messages translated line by line, keeping `[date time] Name:` so you still see who said what. |
| **Forward a voice note** | Forward any Italian voice message you don't understand to the bot: it comes back transcribed, translated, and **as a voice note in your language**. |
| **Reply in your language** | Record a voice note to the bot in your language: it comes back transcribed, translated into natural Italian, and voiced. One tap and your account posts text + voice to the group. |

## Implementation

One Python process, one file ([bot.py](bot.py)), two Telethon clients on the same asyncio loop:

- **User client** (MTProto, the student's own account): lists groups, reads messages, posts the
  confirmed reply. Logs in once interactively; the session is stored in `user.session`.
- **Bot client** (BotFather token): the UI. Inline buttons, private chat only, and it answers
  **only the `OWNER_ID`** configured in `.env`; everyone else is ignored.

External services:

- **Gemma 4** via the Gemini API (`google-genai` SDK), model `gemma-4-26b-a4b-it`, for summaries and
  translations. Thinking is set to `minimal`: the default reasoning cost ~1,000 hidden tokens and tripled
  latency, which brought a 50-message summary from 30-80 s down to ~10 s. Calls are retried with
  exponential backoff and fall back to `gemma-4-31b-it` when the backend returns 500s.
- **ElevenLabs**: `eleven_v4` text-to-speech with `opus_48000_64` output (an OGG/Opus file, which Telegram
  accepts directly as a voice note, so no ffmpeg) and `scribe_v2` speech-to-text.

Design choices:

- Messages are sent to the model as `[dd/mm HH:MM] Name: text`, one line each, raw text without
  Telegram markup, local time. Media without text is skipped.
- A voice note sent to the bot is routed by its forward header: forwarded means "translate this for me",
  recorded means "post this to the group for me".
- Every handler is wrapped by a small guard: owner check, and any API error becomes a `❌` message
  in chat instead of crashing the process.
- No database, no framework: the only state is the last selected group and the pending reply draft.

Dependencies: `telethon`, `python-dotenv`, `google-genai`, `elevenlabs`.

## How to run

1. Create a venv and activate it
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   ```
2. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill it in:
   - `API_ID`, `API_HASH` from https://my.telegram.org (API development tools)
   - `PHONE`, your Telegram number in international format
   - `BOT_TOKEN` from @BotFather, `OWNER_ID` from @userinfobot
   - `GEMINI_API_KEY` from https://aistudio.google.com/apikey
   - `ELEVENLABS_API_KEY` (Text to Speech + Speech to Text access) and `ELEVENLABS_VOICE_ID`
   - `TARGET_LANG` (ISO code, default `en`) and `SUMMARY_LIMIT` (default 100)
4. Start the bot. The first run asks for the Telegram login code in the terminal; after that the
   session is saved and it starts straight away.
   ```bash
   python bot.py
   ```
5. In Telegram, open your bot, send `/start`, pick a group, tap a button.
   Forward it any Italian voice note to get it back in your language.
   To reply in the group, record a voice note to the bot and confirm with the ✅ button.
