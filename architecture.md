# Architecture

![System architecture](docs/architecture.svg)

| Component | Role |
|---|---|
| <img src="docs/telegram.svg" width="20"> Erasmus student | Private chat with the bot |
| <img src="docs/python.svg" width="70"> `bot.py` | One asyncio process, two Telethon clients |
| Bot client | UI: buttons, voice notes (BotFather token) |
| User client | Reads the groups, posts the reply (student's account, no bot in the group) |
| <img src="docs/gemma.svg" width="22"> Gemma 4 | `gemma-4-26b-a4b-it` |
| <img src="docs/elevenlabs-symbol.svg" width="20"> ElevenLabs | `eleven_v4` TTS · `scribe_v2` STT |

## Flows

```mermaid
sequenceDiagram
    actor S as Student
    participant B as bot.py
    participant T as Telegram
    participant G as Gemma 4
    participant E as ElevenLabs

    rect rgb(255, 248, 230)
    Note over S,E: 📝 Summary / 🌐 Translate
    S->>B: tap group → tap button
    B->>T: last N messages (user client)
    B->>G: summarize / translate
    B-->>S: text
    B->>E: TTS (summary only)
    B-->>S: voice note
    end

    rect rgb(238, 244, 255)
    Note over S,E: 🎙️ Forwarded voice note
    S->>B: forward Italian voice note
    B->>E: STT
    B->>G: translate
    B->>E: TTS
    B-->>S: voice note in student's language
    end

    rect rgb(244, 244, 245)
    Note over S,E: 🗣️ Reply in the group
    S->>B: record voice note
    B->>E: STT
    B->>G: translate to Italian
    B->>E: TTS
    B-->>S: Italian voice note + ✅
    S->>B: tap ✅
    B->>T: post text + voice (user client)
    end
```
