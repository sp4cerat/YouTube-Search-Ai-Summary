#!/usr/bin/env python3
"""
YouTube Search + Transcript Summary Server
-------------------------------------------
Endpoints:
  GET  /                     → serves the frontend
  GET  /api/search?q=...&page=1  → search YouTube videos
  GET  /api/transcript/<id>  → fetch transcript for a video
  POST /api/summary          → fetch transcript + summarize via LLM

Config: config.json (LLM provider, model, API key, server settings)
"""

import json
import os
import re
import requests
from flask import Flask, jsonify, request, send_from_directory
from youtube_transcript_api import YouTubeTranscriptApi

# ── Load config ──────────────────────────────────────────────────────────────

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

with open(CONFIG_PATH, "r") as f:
    CONFIG = json.load(f)

LLM = CONFIG["llm"]
SERVER = CONFIG["server"]
YT = CONFIG["youtube"]

app = Flask(__name__, static_folder="static")


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/search")
def search_videos():
    """Search YouTube via Innertube API (single request, full metadata)."""
    query = request.args.get("q", "").strip()
    continuation = request.args.get("continuation", "")
    per_page = YT.get("results_per_page", 10)

    if not query and not continuation:
        return jsonify({"error": "Missing query parameter 'q'"}), 400

    try:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        if continuation:
            # Load more results via continuation token
            payload = {
                "context": {
                    "client": {
                        "clientName": "WEB",
                        "clientVersion": "2.20240101.00.00",
                        "hl": "de",
                        "gl": "DE",
                    }
                },
                "continuation": continuation,
            }
            resp = requests.post(
                "https://www.youtube.com/youtubei/v1/search?prettyPrint=false",
                headers=headers,
                json=payload,
                timeout=15,
            )
        else:
            # Initial search
            payload = {
                "context": {
                    "client": {
                        "clientName": "WEB",
                        "clientVersion": "2.20240101.00.00",
                        "hl": "de",
                        "gl": "DE",
                    }
                },
                "query": query,
            }
            resp = requests.post(
                "https://www.youtube.com/youtubei/v1/search?prettyPrint=false",
                headers=headers,
                json=payload,
                timeout=15,
            )

        resp.raise_for_status()
        data = resp.json()

        # Parse results from Innertube response
        videos = []
        next_continuation = ""

        # Extract video items from the nested response structure
        contents = []
        if continuation:
            # Continuation response structure
            actions = data.get("onResponseReceivedCommands", [])
            for action in actions:
                items = (
                    action.get("appendContinuationItemsAction", {})
                    .get("continuationItems", [])
                )
                contents.extend(items)
        else:
            # Initial search response structure
            sections = (
                data.get("contents", {})
                .get("twoColumnSearchResultsRenderer", {})
                .get("primaryContents", {})
                .get("sectionListRenderer", {})
                .get("contents", [])
            )
            for section in sections:
                items = (
                    section.get("itemSectionRenderer", {})
                    .get("contents", [])
                )
                contents.extend(items)
                # Check for continuation token in section list
                ct = section.get("continuationItemRenderer", {})
                if ct:
                    next_continuation = (
                        ct.get("continuationEndpoint", {})
                        .get("continuationCommand", {})
                        .get("token", "")
                    )

        for item in contents:
            # Check for continuation token
            ct = item.get("continuationItemRenderer", {})
            if ct:
                next_continuation = (
                    ct.get("continuationEndpoint", {})
                    .get("continuationCommand", {})
                    .get("token", "")
                )
                continue

            renderer = item.get("videoRenderer")
            if not renderer:
                continue

            vid_id = renderer.get("videoId", "")

            # Title
            title_runs = renderer.get("title", {}).get("runs", [])
            title = "".join(r.get("text", "") for r in title_runs)

            # Channel
            channel_runs = (
                renderer.get("ownerText", {}).get("runs", [])
                or renderer.get("longBylineText", {}).get("runs", [])
            )
            channel = "".join(r.get("text", "") for r in channel_runs)

            # Duration
            duration_text = (
                renderer.get("lengthText", {}).get("simpleText", "")
            )

            # Views - extract raw number
            view_text = renderer.get("viewCountText", {}).get("simpleText", "")
            view_count = 0
            if view_text:
                digits = re.sub(r"[^\d]", "", view_text)
                view_count = int(digits) if digits else 0

            # Format views for display
            if view_count >= 1_000_000:
                views = f"{view_count / 1_000_000:.1f}M views"
            elif view_count >= 1_000:
                views = f"{view_count / 1_000:.1f}K views"
            elif view_count > 0:
                views = f"{view_count} views"
            else:
                views = view_text  # fallback to raw text (e.g. live streams)

            # Published date
            published_text = renderer.get("publishedTimeText", {}).get("simpleText", "")

            # Thumbnail
            thumbs = renderer.get("thumbnail", {}).get("thumbnails", [])
            thumb_url = thumbs[-1]["url"] if thumbs else f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg"

            videos.append(
                {
                    "id": vid_id,
                    "title": title,
                    "channel": channel,
                    "duration": duration_text,
                    "views": views,
                    "view_count": view_count,
                    "published": published_text,
                    "thumbnail": thumb_url,
                    "url": f"https://www.youtube.com/watch?v={vid_id}",
                }
            )

        has_more = bool(next_continuation)

        return jsonify({
            "videos": videos,
            "has_more": has_more,
            "continuation": next_continuation,
        })

    except requests.exceptions.Timeout:
        return jsonify({"error": "Suche hat zu lange gedauert"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/transcript/<video_id>")
def get_transcript(video_id):
    """Fetch the transcript/captions for a YouTube video."""
    langs = YT.get("transcript_languages", ["de", "en"])

    try:
        ytt = YouTubeTranscriptApi()
        entries = ytt.fetch(video_id, languages=langs)

        # Build full text
        full_text = " ".join(
            snippet.text for snippet in entries
        )
        # Also return structured entries
        structured = [
            {
                "start": round(snippet.start, 1),
                "duration": round(snippet.duration, 1),
                "text": snippet.text,
            }
            for snippet in entries
        ]

        lang_code = getattr(entries, "language_code", langs[0] if langs else "en")

        return jsonify(
            {
                "video_id": video_id,
                "language": lang_code,
                "text": full_text,
                "segments": structured,
            }
        )

    except Exception as e:
        return jsonify({"error": f"Transcript-Fehler: {str(e)}"}), 500


@app.route("/api/summary", methods=["POST"])
def summarize():
    """Fetch transcript and summarize it via the configured LLM."""
    data = request.get_json() or {}
    video_id = data.get("video_id", "")
    video_title = data.get("title", "Video")

    if not video_id:
        return jsonify({"error": "video_id fehlt"}), 400

    # Step 1: Get transcript
    langs = YT.get("transcript_languages", ["de", "en"])
    try:
        ytt = YouTubeTranscriptApi()
        entries = ytt.fetch(video_id, languages=langs)
        full_text = " ".join(snippet.text for snippet in entries)
        lang_code = getattr(entries, "language_code", langs[0] if langs else "en")

    except Exception as e:
        return jsonify({"error": f"Transcript-Fehler: {str(e)}"}), 500

    # Truncate very long transcripts (most LLMs handle ~100k tokens)
    max_chars = 80_000
    if len(full_text) > max_chars:
        full_text = full_text[:max_chars] + "\n\n[... Transcript gekürzt ...]"

    # Step 2: Summarize via LLM
    summary_lang = "Deutsch" if lang_code.startswith("de") else "der Sprache des Transcripts"

    prompt = f"""Fasse das folgende YouTube-Video-Transcript zusammen.

Video-Titel: {video_title}

Erstelle eine strukturierte Zusammenfassung auf {summary_lang} mit:
1. **Kernaussage** (1-2 Sätze)
2. **Wichtigste Punkte** (3-7 Stichpunkte)
3. **Fazit / Takeaway** (1-2 Sätze)

Transcript:
{full_text}"""

    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM['api_key']}",
        }
        # Support site URL / app name for OpenRouter
        if LLM.get("provider") == "openrouter":
            headers["HTTP-Referer"] = "http://localhost:5000"
            headers["X-Title"] = "YT-Search-Summary"

        payload = {
            "model": LLM["model"],
            "max_tokens": LLM.get("max_tokens", 1024),
            "temperature": LLM.get("temperature", 0.3),
            "messages": [{"role": "user", "content": prompt}],
        }

        resp = requests.post(LLM["api_url"], headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        result = resp.json()

        # Extract text from response (OpenRouter / OpenAI compatible format)
        summary_text = (
            result.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "Keine Zusammenfassung erhalten.")
        )

        return jsonify(
            {
                "video_id": video_id,
                "title": video_title,
                "summary": summary_text,
                "model": LLM["model"],
                "transcript_length": len(full_text),
            }
        )

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"LLM-Fehler: {str(e)}"}), 500


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="YT Search + Transcript Summary Server")
    parser.add_argument("-p", "--port", type=int, default=None, help="Server-Port (überschreibt config.json)")
    parser.add_argument("--host", type=str, default=None, help="Server-Host (überschreibt config.json)")
    parser.add_argument("--debug", action="store_true", default=None, help="Debug-Modus aktivieren")
    args = parser.parse_args()

    host = args.host or SERVER.get("host", "0.0.0.0")
    port = args.port or SERVER.get("port", 5000)
    debug = args.debug if args.debug is not None else SERVER.get("debug", False)

    print(f"🎬 YT Search Server starting on {host}:{port}")
    print(f"🤖 LLM: {LLM['model']} via {LLM['provider']}")
    app.run(host=host, port=port, debug=debug)
