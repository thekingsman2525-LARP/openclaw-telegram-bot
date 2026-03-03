import os
import json
import httpx
import random
from fastapi import FastAPI, Request
from supabase import create_client, Client

app = FastAPI()

# Configuration from Environment Variables (Vercel)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://oftyjihmtjyradyiwhuh.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9mdHlqaWhtdGp5cmFkeWl3aHVoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI1NDU5MzksImV4cCI6MjA4ODEyMTkzOX0.h88jM4Lm6SSGtlEqqKRmqvas4Tjs3HgSrWkPW1LLGc4")

# Initialize Supabase Client
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    supabase = None
    print(f"Supabase connection failed: {e}")

# ==========================================
# TELEGRAM API HELPERS
# ==========================================
def tg_request(method: str, payload: dict):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"
    if "reply_markup" in payload and isinstance(payload["reply_markup"], dict):
        payload["reply_markup"] = json.dumps(payload["reply_markup"])
    try:
        httpx.post(url, json=payload, timeout=10.0)
    except Exception as e:
        print(f"Telegram API Error: {e}")

# ==========================================
# KEYBOARD MENUS
# ==========================================
def get_level_1_menu(file_id: str, media_type: str):
    """Initial Golden/Slop selection."""
    return {
        "inline_keyboard": [
            [
                {"text": "🌟 FLAWLESS", "callback_data": f"golden|{media_type}|{file_id}"},
                {"text": "🔴 FLAWED", "callback_data": f"flawed|{media_type}|{file_id}"}
            ]
        ]
    }

def get_level_2_image_menu(file_id: str):
    """Deep category selection for Images."""
    return {
        "inline_keyboard": [
            [
                {"text": "✋ Anatomy", "callback_data": f"flag|anatomy|{file_id}"},
                {"text": "🧴 Texture/Skin", "callback_data": f"flag|texture|{file_id}"}
            ],
            [
                {"text": "👗 Outfit/Context", "callback_data": f"flag|context|{file_id}"},
                {"text": "👤 Lost Persona", "callback_data": f"flag|persona|{file_id}"}
            ],
            [
                {"text": "✅ SUBMIT FLAGS", "callback_data": f"submit_flaws|image|{file_id}"},
                {"text": "✏️ TYPE NOTE", "callback_data": f"typenote|{file_id}"}
            ]
        ]
    }

def get_level_2_video_menu(file_id: str):
    """Deep category selection for Videos."""
    return {
        "inline_keyboard": [
            [
                {"text": "⏱️ Flickering", "callback_data": f"flag|flicker|{file_id}"},
                {"text": "🧟 Melting", "callback_data": f"flag|melting|{file_id}"}
            ],
            [
                {"text": "🚶 Bad Physics", "callback_data": f"flag|physics|{file_id}"},
                {"text": "👤 Lost Persona", "callback_data": f"flag|persona|{file_id}"}
            ],
            [
                {"text": "✅ SUBMIT FLAGS", "callback_data": f"submit_flaws|video|{file_id}"},
                {"text": "✏️ TYPE NOTE", "callback_data": f"typenote|{file_id}"}
            ]
        ]
    }

# Temporary memory to store multi-selected flags before submission (since Vercel is stateless)
# In production with thousands of users, this should use Vercel KV, but a global dict works for a 2-man team MVP.
ACTIVE_SESSIONS = {}

# ==========================================
# WEBHOOK ENDPOINT
# ==========================================
@app.post("/webhook")
async def telegram_webhook(request: Request):
    update = await request.json()
    
    # 1. HANDLE REGULAR MESSAGES (COMMANDS OR REPLIES)
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        username = msg.get("from", {}).get("username", "Unknown")
        text = msg.get("text", "")

        # CMD: /swipe
        if text.startswith("/swipe"):
            # TODO: Pull a real `file_id` from your dump channel. 
            # For testing, we simulate sending a message that asks you to upload something to test the buttons.
            tg_request("sendMessage", {
                "chat_id": chat_id,
                "text": "Send me a photo or video to begin the swipe loop!"
            })
            return {"status": "ok"}
            
        # Catch media uploads (Acts as our "Dump Channel" hook for testing)
        if "photo" in msg:
            file_id = msg["photo"][-1]["file_id"]
            tg_request("sendPhoto", {
                "chat_id": chat_id,
                "photo": file_id,
                "caption": "How is this generated Image?",
                "reply_markup": get_level_1_menu(file_id, "image")
            })
        elif "video" in msg:
            file_id = msg["video"]["file_id"]
            tg_request("sendVideo", {
                "chat_id": chat_id,
                "video": file_id,
                "caption": "How is this generated Video?",
                "reply_markup": get_level_1_menu(file_id, "video")
            })
            
        # Catch ForceReply (Typed Notes)
        if "reply_to_message" in msg:
            reply_text = msg["reply_to_message"].get("text", "")
            if "Type your critique" in reply_text:
                # The user just typed a custom note! Let's log it to Supabase.
                # Format of the prompt was: "Type your critique for file_id: <file_id>"
                try:
                    target_file_id = reply_text.split("file_id: ")[1]
                    if supabase:
                        supabase.table("training_data").insert({
                            "file_id": target_file_id,
                            "media_type": "unknown", # Will be updated if we build relational tables
                            "status": "CRITIQUED",
                            "flaw_tags": [],
                            "user_notes": text,
                            "reviewer_name": username
                        }).execute()
                    tg_request("sendMessage", {"chat_id": chat_id, "text": "✅ Custom Typed Text Saved to Supabase Database!"})
                except Exception as e:
                    print(f"Failed to log typed note: {e}")

    # 2. HANDLE BUTTON CLICKS (CALLBACK QUERIES)
    elif "callback_query" in update:
        call = update["callback_query"]
        chat_id = call["message"]["chat"]["id"]
        msg_id = call["message"]["message_id"]
        data = call["data"]
        username = call["from"].get("username", "Unknown")

        # Answer the callback to stop the loading circle on Telegram UI
        tg_request("answerCallbackQuery", {"callback_query_id": call["id"]})

        parts = data.split("|")
        action = parts[0]

        # Action: GOLDEN
        if action == "golden":
            media_type, file_id = parts[1], parts[2]
            if supabase:
                supabase.table("training_data").insert({
                    "file_id": file_id,
                    "media_type": media_type,
                    "status": "GOLDEN",
                    "flaw_tags": [],
                    "reviewer_name": username
                }).execute()
            
            tg_request("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": msg_id, "reply_markup": {"inline_keyboard": []}})
            tg_request("sendMessage", {"chat_id": chat_id, "text": "✅ Logged as Flawless in Supabase."})

        # Action: FLAWED -> Show Level 2
        elif action == "flawed":
            media_type, file_id = parts[1], parts[2]
            ACTIVE_SESSIONS[file_id] = [] # Initialize empty flags list
            menu = get_level_2_image_menu(file_id) if media_type == "image" else get_level_2_video_menu(file_id)
            tg_request("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": msg_id, "reply_markup": menu})

        # Action: TOGGLE A FLAG (Multi-select)
        elif action == "flag":
            flag_name, file_id = parts[1], parts[2]
            if file_id not in ACTIVE_SESSIONS: ACTIVE_SESSIONS[file_id] = []
            
            if flag_name in ACTIVE_SESSIONS[file_id]:
                ACTIVE_SESSIONS[file_id].remove(flag_name)
            else:
                ACTIVE_SESSIONS[file_id].append(flag_name)
                
            # Note: In a production bot, we would edit the keyboard here to prepend a "✅" checkmark to the selected button text.
            tg_request("sendMessage", {"chat_id": chat_id, "text": f"Flag added: {flag_name}"})

        # Action: SUBMIT FLAGS
        elif action == "submit_flaws":
            media_type, file_id = parts[1], parts[2]
            flags = ACTIVE_SESSIONS.get(file_id, [])
            
            if supabase:
                supabase.table("training_data").insert({
                    "file_id": file_id,
                    "media_type": media_type,
                    "status": "SLOP",
                    "flaw_tags": flags,
                    "reviewer_name": username
                }).execute()
            
            # Clear buttons
            tg_request("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": msg_id, "reply_markup": {"inline_keyboard": []}})
            tg_request("sendMessage", {"chat_id": chat_id, "text": f"✅ Submitted to Supabase with flags: {flags}"})
            
            if file_id in ACTIVE_SESSIONS: del ACTIVE_SESSIONS[file_id]

        # Action: TYPE CUSTOM NOTE
        elif action == "typenote":
            file_id = parts[1]
            tg_request("sendMessage", {
                "chat_id": chat_id,
                "text": f"Type your critique for file_id: {file_id}\n(Reply directly to this message)",
                "reply_markup": {"force_reply": True}
            })

    return {"status": "ok"}
