"""
Slack -> AI -> Confluence monitor.

Listens to a Slack channel. For each new message, asks Claude whether the
message is related to a target topic. If it is, Claude writes a short note,
which is appended to a Confluence page.

Setup
-----
1. Create a Slack app (https://api.slack.com/apps) with Socket Mode enabled.
   - Bot token scopes: channels:history, channels:read, chat:write
   - Event subscriptions (bot events): message.channels
   - Install to workspace; grab the Bot User OAuth Token (xoxb-...) and the
     App-Level Token (xapp-..., with connections:write scope).
   - Invite the bot to the channel you want to watch: /invite @yourbot
2. Get an Anthropic API key: https://console.anthropic.com/
3. Get a Confluence API token: https://id.atlassian.com/manage-profile/security/api-tokens
   - You also need your Confluence base URL, your account email, and the
     numeric page ID of the page to append notes to.

Environment variables (see .env.example):
   SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_CHANNEL_ID
   ANTHROPIC_API_KEY
   CONFLUENCE_BASE_URL, CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN, CONFLUENCE_PAGE_ID
   TOPIC

Install:
   pip install slack-bolt anthropic requests python-dotenv

Run:
   python slack_confluence_monitor.py
"""

import os
import json
import logging
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from anthropic import Anthropic
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("monitor")

# --- Config ---------------------------------------------------------------
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]
SLACK_CHANNEL_ID = os.environ["SLACK_CHANNEL_ID"]

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")

CONFLUENCE_BASE_URL = os.environ["CONFLUENCE_BASE_URL"].rstrip("/")
CONFLUENCE_EMAIL = os.environ["CONFLUENCE_EMAIL"]
CONFLUENCE_API_TOKEN = os.environ["CONFLUENCE_API_TOKEN"]
CONFLUENCE_PAGE_ID = os.environ["CONFLUENCE_PAGE_ID"]

# The topic you care about. Be specific for best classification accuracy.
TOPIC = os.environ.get(
    "TOPIC",
    "production incidents, outages, or service degradations affecting customers",
)

client = Anthropic(api_key=ANTHROPIC_API_KEY)
app = App(token=SLACK_BOT_TOKEN)


# --- AI: classify + summarize ---------------------------------------------
def analyze_message(text: str) -> dict:
    """Ask Claude if the message is on-topic; if so, produce a note.

    Returns {"relevant": bool, "note": str}. Falls back to not-relevant on
    any parsing error so we never post garbage to Confluence.
    """
    prompt = f"""You are monitoring a Slack channel for messages related to this topic:

TOPIC: {TOPIC}

Here is a Slack message:
---
{text}
---

Decide whether this message is related to the topic. If it is, write a concise
note (1-3 sentences) capturing the key information worth recording.

Respond with ONLY a JSON object, no preamble or markdown fences:
{{"relevant": true or false, "note": "the note text, or empty string if not relevant"}}"""

    resp = client.messages.create(
        model=MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = "".join(b.text for b in resp.content if b.type == "text").strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(raw)
        return {"relevant": bool(data.get("relevant")), "note": data.get("note", "")}
    except (json.JSONDecodeError, AttributeError):
        log.warning("Could not parse model output: %r", raw)
        return {"relevant": False, "note": ""}


# --- Confluence: append a note to a page ----------------------------------
def append_to_confluence(note: str, author: str) -> None:
    """Fetch the current page body, append a note, and update the page.

    Confluence requires the full body and an incremented version number on
    update, so we read-modify-write.
    """
    auth = (CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN)
    headers = {"Content-Type": "application/json"}
    base = f"{CONFLUENCE_BASE_URL}/wiki/rest/api/content/{CONFLUENCE_PAGE_ID}"

    # Read current body + version.
    r = requests.get(
        base, params={"expand": "body.storage,version"}, auth=auth, timeout=30
    )
    r.raise_for_status()
    page = r.json()

    title = page["title"]
    version = page["version"]["number"]
    body = page["body"]["storage"]["value"]

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # Storage format is XHTML. Escape angle brackets in user content.
    safe_note = note.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_author = author.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    entry = f"<p><strong>{ts}</strong> (from {safe_author}): {safe_note}</p>"

    payload = {
        "id": CONFLUENCE_PAGE_ID,
        "type": "page",
        "title": title,
        "version": {"number": version + 1},
        "body": {"storage": {"value": body + entry, "representation": "storage"}},
    }
    r = requests.put(base, data=json.dumps(payload), auth=auth, headers=headers, timeout=30)
    r.raise_for_status()
    log.info("Appended note to Confluence page %s", CONFLUENCE_PAGE_ID)


# --- Slack event handler ---------------------------------------------------
@app.event("message")
def handle_message(event, say):
    # Only watch the target channel; ignore bot messages, edits, joins, etc.
    if event.get("channel") != SLACK_CHANNEL_ID:
        return
    if event.get("bot_id") or event.get("subtype"):
        return

    text = event.get("text", "").strip()
    if not text:
        return

    log.info("New message: %s", text[:120])
    try:
        result = analyze_message(text)
    except Exception:
        log.exception("AI analysis failed")
        return

    if not result["relevant"]:
        log.info("Not relevant to topic; skipping.")
        return

    user = event.get("user", "unknown")
    try:
        append_to_confluence(result["note"], author=user)
    except Exception:
        log.exception("Confluence update failed")
        return

    # Optional: confirm in-thread.
    say(text="Logged this to Confluence.", thread_ts=event.get("ts"))


if __name__ == "__main__":
    log.info("Watching channel %s for topic: %s", SLACK_CHANNEL_ID, TOPIC)
    SocketModeHandler(app, SLACK_APP_TOKEN).start()
