import os
import json
import httpx
from fastapi import FastAPI, Request
from supabase import create_client, Client

app = FastAPI()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8775175120:AAFu9ErQmn1uwLA8O5b0zr2qANhC97Qhaxs")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://oftyjihmtjyradyiwhuh.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9mdHlqaWhtdGp5cmFkeWl3aHVoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI1NDU5MzksImV4cCI6MjA4ODEyMTkzOX0.h88jM4Lm6SSGtlEqqKRmqvas4Tjs3HgSrWkPW1LLGc4")

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    SUPA_ERR = None
except Exception as e:
    supabase = None
    SUPA_ERR = str(e)
    print(f"Supabase connection failed: {e}")

def tg_request(method: str, payload: dict):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"
    if "reply_markup" in payload and isinstance(payload["reply_markup"], dict):
        payload["reply_markup"] = json.dumps(payload["reply_markup"])
    try:
        httpx.post(url, json=payload, timeout=10.0)
    except Exception as e:
        print(f"Telegram API Error: {e}")

# KEYBOARD MENUS
def get_level_1_menu(file_id: str, media_type: str, is_test: bool = False):
    t = "|test" if is_test else ""
    return {"inline_keyboard": [[
        {"text": "🌟 FLAWLESS", "callback_data": f"golden|{media_type}|{file_id}{t}"},
        {"text": "🔴 FLAWED", "callback_data": f"flawed|{media_type}|{file_id}{t}"}
    ]]}

def get_level_2_image_menu(file_id: str, is_test: bool = False):
    t = "|test" if is_test else ""
    return {"inline_keyboard": [
        [{"text": "✋ Anatomy", "callback_data": f"flag|anatomy|{file_id}{t}"}, {"text": "🧴 Texture/Skin", "callback_data": f"flag|texture|{file_id}{t}"}],
        [{"text": "👗 Outfit/Context", "callback_data": f"flag|context|{file_id}{t}"}, {"text": "👤 Lost Persona", "callback_data": f"flag|persona|{file_id}{t}"}],
        [{"text": "✅ SUBMIT FLAGS", "callback_data": f"submit_flaws|image|{file_id}{t}"}, {"text": "✏️ TYPE NOTE", "callback_data": f"typenote|{file_id}{t}"}]
    ]}

def get_level_2_video_menu(file_id: str, is_test: bool = False):
    t = "|test" if is_test else ""
    return {"inline_keyboard": [
        [{"text": "⏱️ Flickering", "callback_data": f"flag|flicker|{file_id}{t}"}, {"text": "🧟 Melting", "callback_data": f"flag|melting|{file_id}{t}"}],
        [{"text": "🚶 Bad Physics", "callback_data": f"flag|physics|{file_id}{t}"}, {"text": "👤 Lost Persona", "callback_data": f"flag|persona|{file_id}{t}"}],
        [{"text": "✅ SUBMIT FLAGS", "callback_data": f"submit_flaws|video|{file_id}{t}"}, {"text": "✏️ TYPE NOTE", "callback_data": f"typenote|{file_id}{t}"}]
    ]}

ACTIVE_SESSIONS = {}

def send_next_swipe(chat_id, is_test=False):
    """Fetches the next unrated media from Supabase Media Queue."""
    if not supabase: return
    response = supabase.table("media_queue").select("*").eq("is_rated", False).limit(1).execute()
    data = response.data
    if not data:
        tg_request("sendMessage", {"chat_id": chat_id, "text": "🎉 The queue is empty! You have rated all available media."})
        return
    
    media = data[0]
    file_id = media["file_id"]
    media_type = media["media_type"]
    
    caption_prefix = "🧪 [TEST MODE] " if is_test else ""
    
    if media_type == "image":
        tg_request("sendPhoto", {"chat_id": chat_id, "photo": file_id, "caption": f"{caption_prefix}Rate this Image:", "reply_markup": get_level_1_menu(file_id, "image", is_test)})
    else:
        tg_request("sendVideo", {"chat_id": chat_id, "video": file_id, "caption": f"{caption_prefix}Rate this Video:", "reply_markup": get_level_1_menu(file_id, "video", is_test)})

def mark_as_rated(file_id: str):
    if supabase:
        supabase.table("media_queue").update({"is_rated": True}).eq("file_id", file_id).execute()

@app.post("/webhook")
async def telegram_webhook(request: Request):
    update = await request.json()
    
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        username = msg.get("from", {}).get("username", "Unknown")
        text = msg.get("text", "")

        if text.startswith("/status"):
            if supabase:
                unrated = supabase.table("media_queue").select("id", count="exact").eq("is_rated", False).execute().count
                rated = supabase.table("media_queue").select("id", count="exact").eq("is_rated", True).execute().count
                msg_txt = f"📊 **Database Status**\n✅ Rated: {rated}\n⏳ Remaining: {unrated}"
            else:
                msg_txt = f"Supabase not connected. Error: {SUPA_ERR}"
            tg_request("sendMessage", {"chat_id": chat_id, "text": msg_txt})
            return {"status": "ok"}

        if text.startswith("/gallery"):
            if supabase:
                response = supabase.table("media_queue").select("*").eq("is_rated", False).limit(10).execute()
                media_list = []
                for item in response.data:
                    mtype = "photo" if item["media_type"] == "image" else "video"
                    media_list.append({"type": mtype, "media": item["file_id"]})
                if media_list:
                    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMediaGroup"
                    payload = {"chat_id": chat_id, "media": json.dumps(media_list)}
                    try:
                        httpx.post(url, json=payload, timeout=10.0)
                    except Exception as e:
                        pass
                else:
                    tg_request("sendMessage", {"chat_id": chat_id, "text": "No unrated media found for gallery preview."})
            return {"status": "ok"}

        # Initial Swipe trigger pulls from Media Queue
        if text.startswith("/swipe"):
            send_next_swipe(chat_id, is_test=False)
            return {"status": "ok"}
            
        if text.startswith("/testswipe"):
            send_next_swipe(chat_id, is_test=True)
            return {"status": "ok"}
            
        # Catch manual media uploads
        if "photo" in msg:
            file_id = msg["photo"][-1]["file_id"]
            tg_request("sendPhoto", {"chat_id": chat_id, "photo": file_id, "caption": "How is this manual upload?", "reply_markup": get_level_1_menu(file_id, "image")})
        elif "video" in msg:
            file_id = msg["video"]["file_id"]
            tg_request("sendVideo", {"chat_id": chat_id, "video": file_id, "caption": "How is this manual upload?", "reply_markup": get_level_1_menu(file_id, "video")})
            
        # Text input critique logs
        if "reply_to_message" in msg:
            reply_text = msg["reply_to_message"].get("text", "")
            if "Type your critique" in reply_text:
                try:
                    is_test_mode = "TEST MODE" in reply_text
                    target_file_id = reply_text.split("file_id: ")[1].split("\n")[0].replace(" (TEST MODE)", "").strip()
                    
                    if not is_test_mode:
                        if supabase:
                            supabase.table("training_data").insert({
                                "file_id": target_file_id,
                                "media_type": "unknown",
                                "status": "CRITIQUED",
                                "flaw_tags": [],
                                "user_notes": text,
                                "reviewer_name": username
                            }).execute()
                        tg_request("sendMessage", {"chat_id": chat_id, "text": "✅ Custom Typed Text Saved!"})
                    else:
                        tg_request("sendMessage", {"chat_id": chat_id, "text": f"✅ TEST MODE: Critique '{text}' would have been saved!"})
                except Exception as e:
                    pass

    elif "channel_post" in update:
        msg = update["channel_post"]
        file_id = None
        media_type = None
        
        if "photo" in msg:
            file_id = msg["photo"][-1]["file_id"]
            media_type = "image"
        elif "video" in msg:
            if isinstance(msg["video"], dict):
                file_id = msg["video"]["file_id"]
            else:
                file_id = msg["video"][-1]["file_id"]
            media_type = "video"
            
        if file_id and supabase:
            try:
                supabase.table("media_queue").insert({
                    "file_id": file_id,
                    "media_type": media_type,
                    "is_rated": False
                }).execute()
            except Exception:
                pass

    elif "callback_query" in update:
        call = update["callback_query"]
        chat_id = call["message"]["chat"]["id"]
        msg_id = call["message"]["message_id"]
        data = call["data"]
        username = call["from"].get("username", "Unknown")

        tg_request("answerCallbackQuery", {"callback_query_id": call["id"]})

        parts = data.split("|")
        
        is_test = False
        if parts[-1] == "test":
            is_test = True
            parts.pop()

        action = parts[0]

        if action == "golden":
            media_type, file_id = parts[1], parts[2]
            if not is_test:
                if supabase:
                    supabase.table("training_data").insert({
                        "file_id": file_id,
                        "media_type": media_type,
                        "status": "GOLDEN",
                        "flaw_tags": [],
                        "reviewer_name": username
                    }).execute()
                mark_as_rated(file_id)
                msg_txt = "✅ Logged as Flawless. Loading next..."
            else:
                msg_txt = "✅ TEST MODE: Flawless would have been saved. Loading next..."
                
            tg_request("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": msg_id, "reply_markup": {"inline_keyboard": []}})
            tg_request("sendMessage", {"chat_id": chat_id, "text": msg_txt})
            send_next_swipe(chat_id, is_test)

        elif action == "flawed":
            media_type, file_id = parts[1], parts[2]
            ACTIVE_SESSIONS[file_id] = []
            menu = get_level_2_image_menu(file_id, is_test) if media_type == "image" else get_level_2_video_menu(file_id, is_test)
            tg_request("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": msg_id, "reply_markup": menu})

        elif action == "flag":
            flag_name, file_id = parts[1], parts[2]
            if file_id not in ACTIVE_SESSIONS: ACTIVE_SESSIONS[file_id] = []
            
            if flag_name in ACTIVE_SESSIONS[file_id]:
                ACTIVE_SESSIONS[file_id].remove(flag_name)
            else:
                ACTIVE_SESSIONS[file_id].append(flag_name)
                
            tg_request("sendMessage", {"chat_id": chat_id, "text": f"Flag toggled: {flag_name}"})

        elif action == "submit_flaws":
            media_type, file_id = parts[1], parts[2]
            flags = ACTIVE_SESSIONS.get(file_id, [])
            
            if not is_test:
                if supabase:
                    supabase.table("training_data").insert({
                        "file_id": file_id,
                        "media_type": media_type,
                        "status": "SLOP",
                        "flaw_tags": flags,
                        "reviewer_name": username
                    }).execute()
                mark_as_rated(file_id)
                msg_txt = f"✅ Submitted flaws: {flags}. Loading next..."
            else:
                msg_txt = f"✅ TEST MODE: Flaws {flags} would have been saved! Loading next..."
            
            tg_request("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": msg_id, "reply_markup": {"inline_keyboard": []}})
            tg_request("sendMessage", {"chat_id": chat_id, "text": msg_txt})
            if file_id in ACTIVE_SESSIONS: del ACTIVE_SESSIONS[file_id]
            send_next_swipe(chat_id, is_test)

        elif action == "typenote":
            file_id = parts[1]
            test_str = " (TEST MODE)" if is_test else ""
            tg_request("sendMessage", {
                "chat_id": chat_id,
                "text": f"Type your critique for file_id: {file_id}{test_str}\n(Reply directly to this message)",
                "reply_markup": {"force_reply": True}
            })

    return {"status": "ok"}
