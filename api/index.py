import os
import json
import httpx
import random
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
        resp = httpx.post(url, json=payload, timeout=10.0)
        if resp.status_code != 200:
            print(f"Telegram API Error [{resp.status_code}]: {resp.text}")
    except Exception as e:
        print(f"Telegram Web HTTP Error: {e}")

# KEYBOARD MENUS
def get_main_keyboard():
    return {
        "keyboard": [
            [{"text": "/swipe"}, {"text": "/testswipe"}],
            [{"text": "/status"}, {"text": "/gallery"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

def get_level_1_menu(queue_id: str, is_test: bool = False):
    t = "|test" if is_test else ""
    return {"inline_keyboard": [[
        {"text": "🌟 FLAWLESS", "callback_data": f"golden|{queue_id}{t}"},
        {"text": "🔴 FLAWED", "callback_data": f"flawed|{queue_id}{t}"}
    ]]}

def get_level_2_image_menu(queue_id: str, is_test: bool = False):
    t = "|test" if is_test else ""
    return {"inline_keyboard": [
        [{"text": "✋ Anatomy", "callback_data": f"flag|anatomy|{queue_id}{t}"}, {"text": "🧴 Texture/Skin", "callback_data": f"flag|texture|{queue_id}{t}"}],
        [{"text": "👗 Outfit/Context", "callback_data": f"flag|context|{queue_id}{t}"}, {"text": "👤 Lost Persona", "callback_data": f"flag|persona|{queue_id}{t}"}],
        [{"text": "✅ SUBMIT FLAGS", "callback_data": f"submit_flaws|{queue_id}{t}"}, {"text": "✏️ TYPE NOTE", "callback_data": f"typenote|{queue_id}{t}"}]
    ]}

def get_level_2_video_menu(queue_id: str, is_test: bool = False):
    t = "|test" if is_test else ""
    return {"inline_keyboard": [
        [{"text": "⏱️ Flickering", "callback_data": f"flag|flicker|{queue_id}{t}"}, {"text": "🧟 Melting", "callback_data": f"flag|melting|{queue_id}{t}"}],
        [{"text": "🚶 Bad Physics", "callback_data": f"flag|physics|{queue_id}{t}"}, {"text": "👤 Lost Persona", "callback_data": f"flag|persona|{queue_id}{t}"}],
        [{"text": "✅ SUBMIT FLAGS", "callback_data": f"submit_flaws|{queue_id}{t}"}, {"text": "✏️ TYPE NOTE", "callback_data": f"typenote|{queue_id}{t}"}]
    ]}

ACTIVE_SESSIONS = {}

def send_next_swipe(chat_id, is_test=False):
    """Fetches the next unrated media from Supabase Media Queue."""
    if not supabase: return
    response = supabase.table("media_queue").select("*").eq("is_rated", False).limit(50).execute()
    data = response.data
    if not data:
        tg_request("sendMessage", {"chat_id": chat_id, "text": "🎉 The queue is empty! You have rated all available media."})
        return
    
    media = random.choice(data) if is_test else data[0]
    queue_id = str(media["id"])
    file_id = media["file_id"]
    media_type = media["media_type"]
    
    caption_prefix = "🧪 [TEST MODE]\n" if is_test else ""
    
    if media_type == "image":
        tg_request("sendPhoto", {"chat_id": chat_id, "photo": file_id, "caption": f"{caption_prefix}Rate this Image:", "reply_markup": get_level_1_menu(queue_id, is_test)})
    else:
        tg_request("sendVideo", {"chat_id": chat_id, "video": file_id, "caption": f"{caption_prefix}Rate this Video:", "reply_markup": get_level_1_menu(queue_id, is_test)})

def mark_as_rated(queue_id: str):
    if supabase:
        supabase.table("media_queue").update({"is_rated": True}).eq("id", queue_id).execute()

@app.post("/webhook")
async def telegram_webhook(request: Request):
    update = await request.json()
    
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        username = msg.get("from", {}).get("username", "Unknown")
        text = msg.get("text", "")

        if text.startswith("/start"):
            tg_request("sendMessage", {
                "chat_id": chat_id, 
                "text": "Welcome to OpenClaw! Use the buttons below to begin.", 
                "reply_markup": get_main_keyboard()
            })
            return {"status": "ok"}

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
                    target_queue_id = reply_text.split("ID: ")[1].split("\n")[0].replace(" (TEST MODE)", "").strip()
                    
                    if not is_test_mode:
                        if supabase:
                            queue_item = supabase.table("media_queue").select("*").eq("id", target_queue_id).execute().data[0]
                            supabase.table("training_data").insert({
                                "file_id": queue_item["file_id"],
                                "media_type": queue_item["media_type"],
                                "status": "CRITIQUED",
                                "flaw_tags": [],
                                "user_notes": text,
                                "reviewer_name": username
                            }).execute()
                            mark_as_rated(target_queue_id)
                            send_next_swipe(chat_id, is_test=False)
                    else:
                        tg_request("sendMessage", {"chat_id": chat_id, "text": f"✅ TEST MODE: Critique '{text}' would have been saved!"})
                        send_next_swipe(chat_id, is_test=True)
                except Exception as e:
                    pass
                    
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

    # Unified Media Ingestion (Catch both DMs and Channel Posts)
    msg_obj = update.get("message") or update.get("channel_post")
    if msg_obj:
        chat_id = msg_obj["chat"]["id"]
        text = msg_obj.get("text", "")
        username = msg_obj.get("from", {}).get("username", "Unknown")
        
        # 1. Catch Media Uploads (Groups, DMs, Channels)
        file_id = None
        media_type = None
        
        if "photo" in msg_obj:
            file_id = msg_obj["photo"][-1]["file_id"]
            media_type = "image"
        elif "video" in msg_obj:
            if isinstance(msg_obj["video"], dict):
                file_id = msg_obj["video"]["file_id"]
            else:
                file_id = msg_obj["video"][-1]["file_id"]
            media_type = "video"
            
        if file_id:
            # Silently push to Queue
            if supabase:
                try:
                    supabase.table("media_queue").insert({
                        "file_id": file_id,
                        "media_type": media_type,
                        "is_rated": False
                    }).execute()
                except Exception:
                    pass
            
            # If it was a direct DM to the bot (not a channel post), ask to rate it immediately
            if "channel_post" not in update:
                menu = get_level_1_menu(file_id, "image") if media_type == "image" else get_level_1_menu(file_id, "video")
                tg_request("sendPhoto" if media_type == "image" else "sendVideo", {
                    "chat_id": chat_id, 
                    "photo": file_id} if media_type == "image" else {"chat_id": chat_id, "video": file_id, 
                    "caption": "How is this manual upload?", 
                    "reply_markup": menu
                })
            
            return {"status": "ok"} # Stop processing further for pure media dumps

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
        
        # Determine the database queue reference
        queue_id = parts[1] if action in ["golden", "flawed", "submit_flaws", "typenote"] else parts[2]
        
        media_type = "image"
        file_id = ""
        # We need the real file_id and media_type from Supabase to log correctly
        if supabase:
            queue_data = supabase.table("media_queue").select("*").eq("id", queue_id).execute().data
            if queue_data:
                media_type = queue_data[0]["media_type"]
                file_id = queue_data[0]["file_id"]

        if action == "golden":
            if not is_test:
                if supabase and file_id:
                    supabase.table("training_data").insert({
                        "file_id": file_id,
                        "media_type": media_type,
                        "status": "GOLDEN",
                        "flaw_tags": [],
                        "reviewer_name": username
                    }).execute()
                mark_as_rated(queue_id)
                msg_txt = "✅ Logged as Flawless. Loading next..."
            else:
                msg_txt = "✅ TEST MODE: Flawless would have been saved. Loading next..."
                
            tg_request("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": msg_id, "reply_markup": {"inline_keyboard": []}})
            tg_request("sendMessage", {"chat_id": chat_id, "text": msg_txt})
            send_next_swipe(chat_id, is_test)

        elif action == "flawed":
            ACTIVE_SESSIONS[queue_id] = []
            menu = get_level_2_image_menu(queue_id, is_test) if media_type == "image" else get_level_2_video_menu(queue_id, is_test)
            tg_request("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": msg_id, "reply_markup": menu})

        elif action == "flag":
            flag_name = parts[1]
            if queue_id not in ACTIVE_SESSIONS: ACTIVE_SESSIONS[queue_id] = []
            
            if flag_name in ACTIVE_SESSIONS[queue_id]:
                ACTIVE_SESSIONS[queue_id].remove(flag_name)
            else:
                ACTIVE_SESSIONS[queue_id].append(flag_name)
                
            tg_request("sendMessage", {"chat_id": chat_id, "text": f"Flag toggled: {flag_name}"})

        elif action == "submit_flaws":
            flags = ACTIVE_SESSIONS.get(queue_id, [])
            
            if not is_test:
                if supabase:
                    supabase.table("training_data").insert({
                        "file_id": file_id,
                        "media_type": media_type,
                        "status": "SLOP",
                        "flaw_tags": flags,
                        "reviewer_name": username
                    }).execute()
                mark_as_rated(queue_id)
                msg_txt = f"✅ Submitted flaws: {flags}. Loading next..."
            else:
                msg_txt = f"✅ TEST MODE: Flaws {flags} would have been saved! Loading next..."
            
            tg_request("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": msg_id, "reply_markup": {"inline_keyboard": []}})
            tg_request("sendMessage", {"chat_id": chat_id, "text": msg_txt})
            if queue_id in ACTIVE_SESSIONS: del ACTIVE_SESSIONS[queue_id]
            send_next_swipe(chat_id, is_test)

        elif action == "typenote":
            test_str = " (TEST MODE)" if is_test else ""
            tg_request("sendMessage", {
                "chat_id": chat_id,
                "text": f"Type your critique for Media ID: {queue_id}{test_str}\n(Reply directly to this message)",
                "reply_markup": {"force_reply": True}
            })
            
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
