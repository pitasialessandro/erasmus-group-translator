import asyncio
import io
import logging
import os

from dotenv import load_dotenv
from elevenlabs.client import AsyncElevenLabs
from google import genai
from google.genai import types
from telethon import Button, TelegramClient, events, utils
from telethon.tl.types import InputMessagesFilterVoice

load_dotenv()
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])
PHONE = os.getenv("PHONE")  # +39...; if missing, asked interactively on first login
TARGET_LANG = os.getenv("TARGET_LANG", "en")
SUMMARY_LIMIT = int(os.getenv("SUMMARY_LIMIT", "100"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

# user = the student's own account (reads groups), bot = the private interface
user = TelegramClient("user", API_ID, API_HASH)
bot = TelegramClient("bot", API_ID, API_HASH)
bot.parse_mode = None  # LLM output may contain * or _ that would break markdown
llm = genai.Client()  # reads GEMINI_API_KEY
LLM_MODEL = "gemma-4-26b-a4b-it"  # 31b is 3.5x slower and flaky (500s)
eleven = AsyncElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")
state = {"chat": None, "draft": None}  # last selected group, pending reply to post

SUMMARY_PROMPT = f"""You help an Erasmus student in Italy who was added to an Italian Telegram group
and does not understand Italian. You receive the latest messages of the group.
Write a short spoken-style briefing in the language with ISO code "{TARGET_LANG}", as a friend
catching the student up on what happened: 2 or 3 short paragraphs of flowing prose, no lists,
no markdown (no "#", no "**", no "*"). Start with what is urgent or has a deadline, then events,
meetings and decisions, then open questions addressed to everyone. Keep names of people, places
and courses as they are, keep dates and times exact. Skip chit-chat. About 150 words.
End with one final line starting with "Deadlines:" listing the dates that matter, or
"Deadlines: none" if there are none."""

TRANSLATE_CHAT_PROMPT = f"""Translate the following Italian group chat into the language with ISO code
"{TARGET_LANG}". Rules: translate every line, one output line per input line, same order;
keep the "[date time] Name:" prefix exactly as it is; keep names, places and course names as they are;
informal tone like the original; no comments, no markdown, nothing but the translated lines."""

TRANSLATE_PROMPT = f"""Translate the following Italian voice-message transcript into the language
with ISO code "{TARGET_LANG}". Output only the translation, nothing else."""

TO_ITALIAN_PROMPT = """Translate the following message into natural, informal Italian, as a student
would write it in a class group chat. Output only the Italian text, nothing else."""


def guard(handler):
    """Only the owner can talk to the bot; API errors become a message instead of a crash."""

    async def wrapped(event):
        if event.sender_id != OWNER_ID:
            return
        try:
            await handler(event)
        except Exception as e:
            log.exception("handler failed")
            await event.respond(f"❌ {type(e).__name__}: {e}")

    return wrapped


async def send_long(event, text):
    # Telegram caps messages at 4096 chars
    for i in range(0, len(text), 4000):
        await event.respond(text[i : i + 4000])


async def ask_llm(system, text):
    log.info("llm input: %d chars", len(text))
    open("last_llm_input.txt", "w").write(text)  # debug: exact text sent to the model
    r = await llm.aio.models.generate_content(
        model=LLM_MODEL,
        contents=text,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=2048,
            # default thinking burns ~1000 tokens and 3x the time; "minimal" is the only level accepted
            thinking_config=types.ThinkingConfig(thinking_level="minimal"),
        ),
    )
    if not r.text:
        raise RuntimeError("empty answer from the model")
    return r.text.strip()


async def read_messages(chat_id, limit):
    lines = []
    async for m in user.iter_messages(chat_id, limit=limit):
        text = " ".join((m.message or "").split())  # raw text (no markup), one line
        if not text:
            continue
        name = utils.get_display_name(m.sender) or "?"
        lines.append(f"[{m.date.astimezone():%d/%m %H:%M}] {name}: {text}")
    lines.reverse()  # chronological order
    return "\n".join(lines)


@bot.on(events.NewMessage(pattern="/start"))
@guard
async def start(event):
    buttons = []
    async for d in user.iter_dialogs():
        if d.is_group:
            buttons.append([Button.inline(d.name[:40], f"g:{d.id}")])
    if not buttons:
        await event.respond("You are not in any group.")
        return
    await event.respond("Pick a group:", buttons=buttons)


@bot.on(events.CallbackQuery(pattern=rb"g:(-?\d+)"))
@guard
async def pick_group(event):
    chat_id = int(event.pattern_match.group(1))
    state["chat"] = chat_id
    name = utils.get_display_name(await user.get_entity(chat_id))
    await event.edit(
        f"📌 {name}",
        buttons=[
            [Button.inline("📝 Summary", f"s:{chat_id}"), Button.inline("🎙️ Voice notes", f"v:{chat_id}")],
            [Button.inline("🌐 Translate", f"t:{chat_id}")],
        ],
    )


@bot.on(events.CallbackQuery(pattern=rb"s:(-?\d+)"))
@guard
async def summary(event):
    chat_id = int(event.pattern_match.group(1))
    await event.answer(f"Reading the last {SUMMARY_LIMIT} messages…")
    text = await read_messages(chat_id, SUMMARY_LIMIT)
    if not text:
        await event.respond("No text messages found.")
        return
    summary_text = await ask_llm(SUMMARY_PROMPT, text)
    await send_long(event, summary_text)
    await send_audio_summary(event, summary_text)


@bot.on(events.CallbackQuery(pattern=rb"t:(-?\d+)"))
@guard
async def translate_chat(event):
    chat_id = int(event.pattern_match.group(1))
    await event.answer(f"Translating the last {SUMMARY_LIMIT} messages…")
    text = await read_messages(chat_id, SUMMARY_LIMIT)
    if not text:
        await event.respond("No text messages found.")
        return
    await send_long(event, await ask_llm(TRANSLATE_CHAT_PROMPT, text))


# ---------- ElevenLabs extras ----------


async def tts(text):
    """Text -> OGG/Opus voice note, ready for send_file(voice_note=True)."""
    chunks = eleven.text_to_speech.convert(
        VOICE_ID, text=text, model_id="eleven_v4", output_format="opus_48000_64"
    )
    buf = io.BytesIO(b"".join([c async for c in chunks]))
    buf.name = "voice.ogg"
    return buf


async def transcribe(data):
    r = await eleven.speech_to_text.convert(model_id="scribe_v2", file=("voice.ogg", data))
    return r.text


async def send_audio_summary(event, text):
    await bot.send_file(event.chat_id, await tts(text), voice_note=True)


@bot.on(events.CallbackQuery(pattern=rb"v:(-?\d+)"))
@guard
async def voices(event):
    chat_id = int(event.pattern_match.group(1))
    await event.answer("Transcribing voice messages…")
    msgs = await user.get_messages(chat_id, limit=5, filter=InputMessagesFilterVoice)
    if not msgs:
        await event.respond("No voice messages found.")
        return
    for m in reversed(msgs):
        original = await transcribe(await user.download_media(m, bytes))
        translated = await ask_llm(TRANSLATE_PROMPT, original)
        name = utils.get_display_name(m.sender) or "?"
        await event.respond(f"🎙️ {name} ({m.date:%d/%m %H:%M})\n\n🇮🇹 {original}\n\n➡️ {translated}")
        await bot.send_file(event.chat_id, await tts(translated), voice_note=True)


@bot.on(events.NewMessage(func=lambda e: e.voice))
@guard
async def reply_draft(event):
    if state["chat"] is None:
        await event.respond("Pick a group with /start first.")
        return
    original = await transcribe(await event.download_media(bytes))
    italian = await ask_llm(TO_ITALIAN_PROMPT, original)
    state["draft"] = italian
    name = utils.get_display_name(await user.get_entity(state["chat"]))
    await event.respond(f"You said: {original}\n\n🇮🇹 {italian}")
    await bot.send_file(
        event.chat_id,
        await tts(italian),
        voice_note=True,
        caption="Post this to the group?",
        buttons=[[Button.inline(f"✅ Send to {name[:30]}", b"send")]],
    )


@bot.on(events.CallbackQuery(data=b"send"))
@guard
async def reply_send(event):
    if not state["draft"]:
        await event.answer("Nothing to send.")
        return
    await user.send_message(state["chat"], state["draft"])
    await user.send_file(state["chat"], await tts(state["draft"]), voice_note=True)
    state["draft"] = None
    await event.edit("✅ Posted to the group.")


async def main():
    # first run: the login code is still typed in the terminal
    await user.start(phone=PHONE or (lambda: input("Phone (+39...): ")))
    await bot.start(bot_token=BOT_TOKEN)
    me = await user.get_me()
    log.info("user client: %s, bot ready", utils.get_display_name(me))
    await bot.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
