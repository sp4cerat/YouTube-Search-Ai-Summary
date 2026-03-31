# YT Search · Transcript Summary

YouTube-Videosuche mit automatischer Transcript-Zusammenfassung via LLM (OpenRouter / Gemini etc.).

## Features

- **YouTube Suche** – Erste 10 Ergebnisse mit "Mehr laden"
- **Video öffnen** – Direktlink zu YouTube
- **Summary** – Transcript automatisch herunterladen und per LLM zusammenfassen
- **Konfigurierbar** – LLM-Modell, API-Key und Server-Einstellungen in `config.json`

## Setup

```bash
# 1. Dependencies installieren
pip install -r requirements.txt

# 2. Config anpassen – API Key eintragen!
nano config.json

# 3. Server starten
python server.py
```

Dann im Browser öffnen: **http://localhost:5000**

## Config (`config.json`)

| Feld | Beschreibung |
|------|-------------|
| `llm.api_key` | Dein OpenRouter API Key |
| `llm.model` | z.B. `google/gemini-2.0-flash-001`, `anthropic/claude-3.5-sonnet`, `openai/gpt-4o-mini` |
| `llm.api_url` | OpenRouter: `https://openrouter.ai/api/v1/chat/completions` |
| `youtube.results_per_page` | Anzahl Videos pro Seite (Standard: 10) |
| `youtube.transcript_languages` | Bevorzugte Transcript-Sprachen, z.B. `["de", "en"]` |
| `server.port` | Server-Port (Standard: 5000) |

## API Endpoints

| Endpoint | Methode | Beschreibung |
|----------|---------|-------------|
| `/api/search?q=...&page=1` | GET | YouTube-Suche |
| `/api/transcript/<video_id>` | GET | Transcript abrufen |
| `/api/summary` | POST | Transcript + LLM-Zusammenfassung |

## Tech Stack

- **Backend:** Python / Flask
- **Transcript:** `youtube-transcript-api` (kostenlos, kein API Key nötig)
- **Suche:** `youtube-search-python` (kostenlos, kein API Key nötig)
- **LLM:** OpenRouter (oder jeder OpenAI-kompatible Endpoint)
