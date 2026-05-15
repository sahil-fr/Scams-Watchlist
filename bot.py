import os
import json
import time
import pytz
import asyncio
import logging
import threading

import telebot
from flask import Flask

from telebot.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)

from apscheduler.schedulers.background import (
    BackgroundScheduler
)

from telethon import TelegramClient

TOKEN = os.environ.get("BOT_TOKEN")

bot = telebot.TeleBot(
    TOKEN,
    parse_mode="HTML"
)

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Running!"

def run_web():

    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )

# Start Flask thread
threading.Thread(
    target=run_web,
    daemon=True
).start()

REVIEW_CHANNEL_ID = -1003289844580
MAIN_CHANNEL_ID = -1002807922369
MAIN_CHANNEL_USERNAME = "FraudsWatchlist"
BOT_USERNAME = "FraudsWatchlistBOT"
REPORT_PNG_URL = "https://t.me/ScamsWatchlist/9"

DATA_FILE = "reports.json"


if os.path.exists(DATA_FILE):
    try:
        with open(DATA_FILE, "r") as f:
            reports = json.load(f)
    except:
        reports = {}
else:
    reports = {}

user_state = {}
user_lock = {}
group_ids = set()
users_db = {}

def save():
    with open(DATA_FILE, "w") as f:
        json.dump(reports, f, indent=2)

def show_main_menu(chat_id):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("Create Report"))
    bot.send_message(chat_id, "Main Menu:", reply_markup=markup)

def get_user_id_by_username(username):

    try:

        if not username:
            return None

        username = str(username).strip()

        # Remove spaces
        username = username.replace(" ", "")

        # Remove @
        username = username.replace("@", "")

        if not username:
            return None

        if username.isdigit():

            return {
                "id": int(username),
                "username": None
            }

        # Telegram username rules:
        # 5-32 chars
        # letters, numbers, underscore

        if len(username) < 4:
            return None

        if len(username) > 32:
            return None

        if not username.replace("_", "").isalnum():
            return None

        clean_username = f"@{username}"

        try:

            chat = bot.get_chat(clean_username)

            # Success
            if chat and hasattr(chat, "id"):

                return {
                    "id": chat.id,
                    "username": clean_username
                }

        except Exception as e:

            # Bot stop nahi hoga
            print(f"Username lookup failed: {e}")

        # Agar Telegram API fail kare
        # Lekin username valid ho
        # Toh continue hone do

        return {
            "id": None,
            "username": clean_username
        }

    except Exception as e:

        # Full crash protection
        print(f"Lookup crash: {e}")

        return None

def main_menu_reply():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        KeyboardButton("Create Report"),
    )
    return markup

def main_menu_reply():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("User Report"), KeyboardButton("Imp Report"))
    return markup

def get_monthly_stats():
    now = datetime.now()
    first_day_this_month = now.replace(day=1)
    last_day_prev_month = first_day_this_month - timedelta(days=1)
    month_name = last_day_prev_month.strftime("%B")
    year = last_day_prev_month.year

    total_lost = 0
    scams_count = 0

    # Reports dictionary se data calculate karna
    for rid, data in reports.items():
        if data.get("approved") and data.get("type") == "User Report":
            scams_count += 1
            amt = data.get("amount", 0)
            total_lost += amt

    return month_name, year, total_lost, scams_count

# --- AUTOMATIC MONTHLY TRIGGER ---
def send_monthly_report_review():
    try:
        month, year, lost, disputes = get_monthly_stats()
        
        report_msg = (
            f"📊 <b>Frauds Watchlist Monthly Dispute Report — {month} {year}</b>\n\n"
            f"<b>{month} {year}</b>\n"
            f"• ${lost:,} reported lost\n"
            f"• {disputes} disputes filed\n\n"
            "Activity declined following previous month’s spike, though marketplace risks remain ongoing.\n\n"
            "✅ Use trusted middleman\n"
            "❌ Avoid rushed deals"
        )

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("✅ Approve & Post", callback_data="approve_monthly"))
        markup.add(InlineKeyboardButton("❌ Reject", callback_data="reject_monthly"))

        bot.send_message(
            REVIEW_CHANNEL_ID, 
            f"<b>ADMIN REVIEW: Monthly Report</b>\n\n{report_msg}", 
            parse_mode="HTML", 
            reply_markup=markup
        )
    except Exception as e:
        print(f"Error in monthly report: {e}")

# --- SCHEDULER SETUP (Error Fix) ---
try:
    # Termux/Mobile ke liye pytz ka use best hai
    indian_tz = pytz.timezone("Asia/Kolkata")
    scheduler = BackgroundScheduler(timezone=indian_tz)
except Exception as e:
    print(f"Timezone error: {e}. Switching to default system time.")
    # Agar tzdata nahi milti toh default local time use hoga
    scheduler = BackgroundScheduler()

# Job scheduling
scheduler.add_job(send_monthly_report_review, 'cron', day=1, hour=9, minute=0)
scheduler.start()

@bot.message_handler(func=lambda m: m.text.startswith("ID:"))
def set_id_from_missrose(m):
    cid = m.chat.id
    try:
        user_id = int(m.text.split(":")[1].strip())
        if cid in user_state:
            user_state[cid]["target_chat_id"] = user_id
            bot.send_message(cid, f"Telegram User ID set to {user_id}")
    except Exception as e:
        bot.send_message(cid, f"Failed to set ID: {e}")

@bot.message_handler(commands=['start'])
def start(msg):
    cid = msg.chat.id
    
    # Jab bhi user /start kare, purani saari state aur lock clear kar dein
    user_state.pop(cid, None)
    user_lock.pop(cid, None)
    
    if msg.chat.type == "private":
        # Yahan hum directly Create Report ka button de rahe hain
        markup = ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("Create Report")
        
        bot.send_message(
            cid,
            "Hello! Click the button below to create a report.\n"
            "If you want to lookup a user you can use /lookup",
            reply_markup=markup
        )

@bot.message_handler(func=lambda msg: msg.text == "Create Report")
def create_report_button(msg):
    cid = msg.chat.id
    # Reset state to ensure fresh start
    user_state[cid] = {"step": "selecting_type"}
    
    # User aur Imp Report buttons upar, Cancel Report niche
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("User Report", "Imp Report")
    markup.row("Cancel Report")
    
    bot.send_message(
        cid,
        "Choose a report type:",
        reply_markup=markup
    )

@bot.message_handler(commands=['lookup'])
def lookup(msg):

    try:

        args = msg.text.split()

        if len(args) < 2:

            bot.send_message(
                msg.chat.id,
                "❌ <b>Usage:</b> <code>/lookup @username</code> or <code>/lookup user_id</code>",
                parse_mode="HTML"
            )

            return

        # ================= CLEAN QUERY =================

        raw_query = args[1].strip()

        query = (
            raw_query
            .replace("@", "")
            .replace("ID:", "")
            .strip()
            .lower()
        )

        found_reports = []

        # ================= LOOP POSTS =================

        for rid, data in reports.items():

            # Approved only
            if not data.get("approved"):
                continue

            # ================= USERNAMES =================

            usernames = [

                str(data.get("target", ""))
                .replace("@", "")
                .replace("ID:", "")
                .strip()
                .lower(),

                str(data.get("fake", ""))
                .replace("@", "")
                .replace("ID:", "")
                .strip()
                .lower()
            ]

            # ================= IDS =================

            ids = [

                str(data.get("target_chat_id", ""))
                .replace("ID:", "")
                .strip(),

                str(data.get("fake_id", ""))
                .replace("ID:", "")
                .strip()
            ]

            matched = False

            # Username match
            if query in usernames:
                matched = True

            # ID match
            if query in ids:
                matched = True

            if matched:

                found_reports.append({

                    "rid": rid,

                    "user": (
                        data.get("target")
                        or data.get("fake")
                        or "Unknown"
                    ),

                    "id": (
                        data.get("target_chat_id")
                        or data.get("fake_id")
                        or "Unknown"
                    ),

                    "link": data.get("msg_link")
                })

        # ================= NO REPORT =================

        if not found_reports:

            bot.send_message(
                msg.chat.id,
                f"No reports found for <code>{raw_query}</code>",
                parse_mode="HTML"
            )

            return

        # ================= FOUND =================

        total = len(found_reports)

        first = found_reports[0]

        bot.send_message(
            msg.chat.id,
            f"⚠️ Reports Found\n\n"
            f"User: {first['user']}\n"
            f"ID: <code>{first['id']}</code>\n"
            f"Total Reports: {total}",
            parse_mode="HTML"
        )

        # ================= BUTTONS =================

        for report in found_reports:

            markup = InlineKeyboardMarkup()

            if report["link"]:

                markup.add(
                    InlineKeyboardButton(
                        "View Report",
                        url=report["link"]
                    )
                )

            bot.send_message(
                msg.chat.id,
                f"📌 <b>Report #{report['rid']}</b>",
                parse_mode="HTML",
                reply_markup=markup
            )

    except Exception as e:

        print(f"Lookup Error: {e}")

        bot.send_message(
            msg.chat.id,
            "❌ Failed to process lookup."
        )

@bot.message_handler(func=lambda m: m.text == "User Report")
def user_report_start(msg):
    cid = msg.chat.id

    user_state[cid] = {
        "step": "target",
        "type": "User Report",
        "reporter": msg.from_user.username or "N/A",
        "chat_id": msg.from_user.id
    }

    bot.send_message(
        cid,
        "Enter the username or user ID of the user you would like to report:"
    )

@bot.message_handler(func=lambda m: m.text == "Imp Report")
def imp_report_start(msg):
    cid = msg.chat.id

    user_state[cid] = {
        "step": "imp_fake",
        "type": "Imp Report",
        "reporter": msg.from_user.username or "N/A",
        "chat_id": msg.from_user.id
    }

    bot.send_message(
        cid,
        "Send the ❌ impersonator's @username:"
    )

@bot.message_handler(func=lambda m: m.text == "Cancel Report")
def cancel_report(msg):
    user_state.pop(msg.chat.id, None)

    bot.send_message(
        msg.chat.id,
        "Your report has been cancelled.",
        reply_markup=ReplyKeyboardRemove()
    )

    start(msg)

@bot.message_handler(func=lambda msg: msg.chat.type == "private")
def handle_steps(msg):

    cid = msg.chat.id
    text = (msg.text or "").strip()

    if text.startswith("/"):
        return

    username_sender = msg.from_user.username or "N/A"
    reporter_chat_id = msg.from_user.id
    forwarded_id = msg.forward_from.id if msg.forward_from else None

    current_time = time.time()

    # ================= ANTI SPAM =================

    if cid in user_lock:
        if current_time - user_lock[cid] < 2:
            return

    user_lock[cid] = current_time

    try:

        # ================= MARKUPS =================

        cancel_markup = ReplyKeyboardMarkup(resize_keyboard=True)
        cancel_markup.row(KeyboardButton("Cancel Report"))

        selection_markup = ReplyKeyboardMarkup(resize_keyboard=True)
        selection_markup.row(
            KeyboardButton("User Report"),
            KeyboardButton("Imp Report")
        )
        selection_markup.row(
            KeyboardButton("Cancel Report")
        )

        # ================= CANCEL =================

        if text == "Cancel Report":

            user_state.pop(cid, None)

            bot.send_message(
                cid,
                "Your report has been cancelled."
            )

            show_main_menu(cid)
            return

        # ================= CREATE REPORT =================

        if text == "Create Report":

            user_state[cid] = {
                "step": "selecting_type"
            }

            bot.send_message(
                cid,
                "Choose the type of report:",
                reply_markup=selection_markup
            )

            return

        # ================= USER REPORT =================

        if text == "User Report":

            user_state[cid] = {
                "step": "target",
                "type": "User Report",
                "reporter": username_sender,
                "chat_id": reporter_chat_id
            }

            only_cancel = ReplyKeyboardMarkup(
                resize_keyboard=True
            )
            only_cancel.row(
                KeyboardButton("Cancel Report")
            )

            bot.send_message(
                cid,
                "Send Scammer's @username, ID, or Forward a message:",
                parse_mode="HTML",
                reply_markup=only_cancel
            )

            return

        # ================= IMP REPORT =================

        if text == "Imp Report":

            user_state[cid] = {
                "step": "imp_fake",
                "type": "Imp Report",
                "reporter": username_sender,
                "chat_id": reporter_chat_id
            }

            only_cancel = ReplyKeyboardMarkup(
                resize_keyboard=True
            )
            only_cancel.row(
                KeyboardButton("Cancel Report")
            )

            bot.send_message(
                cid,
                "Send the ❌ impersonator's @username:",
                parse_mode="HTML",
                reply_markup=only_cancel
            )

            return

        # ================= CHECK STATE =================

        if cid not in user_state:
            return

        step = user_state[cid].get("step")

        # ================= TARGET =================

        if step == "target":

            if forwarded_id:

                user_state[cid]["target_chat_id"] = forwarded_id
                user_state[cid]["target"] = f"ID: {forwarded_id}"

            elif text.isdigit():

                user_state[cid]["target_chat_id"] = int(text)
                user_state[cid]["target"] = f"ID: {text}"

            else:

                result = get_user_id_by_username(text)

                if result is None:

                    bot.send_message(
                        cid,
                        "❌ Invalid username. Please try again with @username.",
                        reply_markup=cancel_markup
                    )

                    return

                user_state[cid]["target"] = (
                    result["username"] or text
                )

                user_state[cid]["target_chat_id"] = (
                    result["id"] or "Unknown"
                )

            user_state[cid]["step"] = "amount"

            bot.send_message(
                cid,
                "Enter the deal value (amount in USD):",
                parse_mode="HTML",
                reply_markup=cancel_markup
            )

            return

        # ================= AMOUNT =================

        elif step == "amount":

            try:

                amount = int(
                    text.replace("$", "")
                    .replace(",", "")
                    .strip()
                )

            except:

                bot.send_message(
                    cid,
                    "❌ Enter a valid amount in numbers only.",
                    reply_markup=cancel_markup
                )

                return

            user_state[cid]["amount"] = amount
            user_state[cid]["step"] = "proof"

            bot.send_message(
                cid,
                "Send the <b>proof link</b>:",
                parse_mode="HTML",
                reply_markup=cancel_markup
            )

            return

        # ================= IMP FAKE =================

        elif step == "imp_fake":

            result = get_user_id_by_username(text)

            if result is None:

                bot.send_message(
                    cid,
                    "❌ Invalid username. Please try again with @username.",
                    reply_markup=cancel_markup
                )

                return

            user_state[cid]["fake"] = (
                result["username"] or text
            )

            user_state[cid]["fake_id"] = (
                result["id"] or "Unknown"
            )

            user_state[cid]["step"] = "imp_real"

            bot.send_message(
                cid,
                "Now send the ✅ real user's @username:",
                reply_markup=cancel_markup
            )

            return

        # ================= IMP REAL =================

        elif step == "imp_real":

            result = get_user_id_by_username(text)

            if result is None:

                bot.send_message(
                    cid,
                    "❌ Invalid username. Please try again with @username.",
                    reply_markup=cancel_markup
                )

                return

            user_state[cid]["real"] = (
                result["username"] or text
            )

            user_state[cid]["real_id"] = (
                result["id"] or "Unknown"
            )

            # DIRECT REVIEW
            user_state[cid]["step"] = "review_wait"

            submit_markup = ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            submit_markup.row(
                KeyboardButton("Submit Report")
            )

            submit_markup.row(
                KeyboardButton("Cancel Report")
            )

            bot.send_message(
                cid,
                "Review your impersonation report and choose an action:",
                reply_markup=submit_markup
            )

            return

        # ================= PROOF =================

        elif step == "proof":

            if not text:

                bot.send_message(
                    cid,
                    "❌ Please send a valid proof link.",
                    reply_markup=cancel_markup
                )

                return

            # Auto add https
            if not text.startswith((
                "http://",
                "https://",
                "tg://"
            )):

                text = "https://" + text

            user_state[cid]["proof"] = text
            user_state[cid]["step"] = "review_wait"

            submit_markup = ReplyKeyboardMarkup(
                resize_keyboard=True
            )

            submit_markup.row(
                KeyboardButton("Submit Report")
            )

            submit_markup.row(
                KeyboardButton("Cancel Report")
            )

            bot.send_message(
                cid,
                "Review your report and choose an action:",
                reply_markup=submit_markup
            )

            return

        # ================= SUBMIT =================

        elif (
            text == "Submit Report"
            and user_state[cid].get("step") == "review_wait"
        ):

            data = user_state[cid]

            rid = str(len(reports) + 1)

            reports[rid] = data.copy()

            save()

            # ---------- IMP REPORT ----------

            if data["type"] == "Imp Report":

                review_text = (
                    f"🟡 <b>IMPERSONATION REVIEW</b>\n\n"
                    f"✅ <b>Real:</b> {data.get('real')}\n"
                    f"🆔 <b>ID:</b> {data.get('real_id')}\n\n"
                    f"❌ <b>Fake:</b> {data.get('fake')}\n"
                    f"🆔 <b>ID:</b> {data.get('fake_id')}"
                )

                success_msg = (
                    "Your impersonation report has been submitted!"
                )

            # ---------- USER REPORT ----------

            else:

                review_text = (
                    f"<b>⚠️ New Report #{rid}</b>\n\n"
                    f"👤 <b>Reporter:</b> @{data.get('reporter')}\n"
                    f"🎯 <b>Target:</b> {data.get('target')}\n"
                    f"🆔 <b>ID:</b> {data.get('target_chat_id')}\n"
                    f"💰 <b>Amount:</b> ${data.get('amount')}\n"
                    f"🔗 <b>Proof:</b> {data.get('proof')}"
                )

                success_msg = (
                    "Your report has been submitted successfully!"
                )

            # ================= REVIEW BUTTONS =================

            markup = InlineKeyboardMarkup()

            markup.add(
                InlineKeyboardButton(
                    "Approve ✅",
                    callback_data=f"approve_{rid}"
                ),
                InlineKeyboardButton(
                    "Reject ❌",
                    callback_data=f"reject_{rid}"
                )
            )

            bot.send_message(
                REVIEW_CHANNEL_ID,
                review_text,
                parse_mode="HTML",
                reply_markup=markup
            )

            bot.send_message(
                cid,
                success_msg
            )

            user_state.pop(cid, None)

            show_main_menu(cid)

    except Exception as e:

        print(f"Error: {e}")

        try:

            bot.send_message(
                cid,
                "❌ An unexpected error occurred. Please try again."
            )

        except:
            pass

    finally:

        user_lock.pop(cid, None)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):

    try:

        if call.data.startswith(("approve_", "reject_")):

            rid = str(call.data.split("_")[1])
            data = reports.get(rid)

            if not data:
                bot.answer_callback_query(call.id, "Report data not found!")
                return

            reporter_id = data.get("chat_id")
            report_type = data.get("type", "User Report")

            if call.data.startswith("approve_"):

                # Prevent double approve
                if data.get("approved"):
                    bot.answer_callback_query(call.id, "Already approved!")
                    return

                # ---------- IMP REPORT ----------
                if report_type == "Imp Report":

                    caption = (
                        f"✅ <b>APPROVED IMPERSONATION REPORT</b>\n\n"
                        f"✅ <b>Real:</b> {data.get('real', 'N/A')}\n"
                        f"🆔 <b>Real ID:</b> {data.get('real_id', 'N/A')}\n\n"
                        f"❌ <b>Fake:</b> {data.get('fake', 'N/A')}\n"
                        f"🆔 <b>Fake ID:</b> {data.get('fake_id', 'N/A')}\n\n"
                        f"🔗 <b>Proof:</b> {data.get('proof', 'N/A')}"
                    )

                    markup = InlineKeyboardMarkup()

                    # Fake profile button
                    if data.get("fake_id"):
                        markup.add(
                            InlineKeyboardButton(
                                "View Fake Profile",
                                url=f"tg://openmessage?user_id={data['fake_id']}"
                            )
                        )

                    # Proof button
                    if data.get("proof"):
                        markup.add(
                            InlineKeyboardButton(
                                "View Proof",
                                url=data["proof"]
                            )
                        )

                    sent = bot.send_photo(
                        MAIN_CHANNEL_ID,
                        REPORT_PNG_URL,
                        caption=caption,
                        parse_mode="HTML",
                        reply_markup=markup
                    )

                # ---------- USER REPORT ----------
                else:

                    t_id = data.get("target_chat_id", "N/A")
                    target_val = str(data.get("target", ""))

                    # Username formatting fix
                    if target_val.startswith("@"):
                        target_username = target_val
                    elif target_val.isdigit():
                        target_username = "Unknown"
                    else:
                        target_username = f"@{target_val}"

                    caption = (
                        f"❌ <b>User:</b> {target_username}\n"
                        f"🆔 <b>Telegram User ID:</b> {t_id}\n"
                        f"⚠️ <b>Status:</b> Flagged"
                    )

                    if data.get("amount"):
                        caption += f"\n💰 <b>Amount Scammed:</b> ${data['amount']}"

                    markup = InlineKeyboardMarkup()

                    buttons = []

                    # Profile button
                    if str(t_id).isdigit():
                        buttons.append(
                            InlineKeyboardButton(
                                "View Profile",
                                url=f"tg://openmessage?user_id={t_id}"
                            )
                        )

                    # Proof button
                    if data.get("proof"):
                        buttons.append(
                            InlineKeyboardButton(
                                "View Proofs",
                                url=data["proof"]
                            )
                        )

                    if buttons:
                        markup.add(*buttons)

                    sent = bot.send_photo(
                        MAIN_CHANNEL_ID,
                        REPORT_PNG_URL,
                        caption=caption,
                        parse_mode="HTML",
                        reply_markup=markup
                    )

                # Save approve status
                reports[rid]["approved"] = True
                save()

                # Notify reporter
                try:
                    bot.send_message(
                        reporter_id,
                        "✅ Your report was approved by moderators and uploaded to the channel."
                    )

                    bot.forward_message(
                        reporter_id,
                        MAIN_CHANNEL_ID,
                        sent.message_id
                    )

                except Exception as e:
                    print(f"Reporter notify failed: {e}")

                # Update admin review message
                try:

                    if call.message.content_type == "photo":

                        bot.edit_message_caption(
                            caption=f"Report #{rid} Approved ✅",
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id
                        )

                    else:

                        bot.edit_message_text(
                            text=f"Report #{rid} Approved ✅",
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id
                        )

                except Exception as e:
                    print(f"Edit approve message failed: {e}")

                bot.answer_callback_query(call.id, "Report approved!")

            # ================= REJECT =================

            elif call.data.startswith("reject_"):

                try:

                    bot.send_message(
                        reporter_id,
                        "❌ Your report was denied. Try again later."
                    )

                except Exception as e:
                    print(f"Reject notify failed: {e}")

                try:

                    if call.message.content_type == "photo":

                        bot.edit_message_caption(
                            caption=f"Report #{rid} Rejected ❌",
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id
                        )

                    else:

                        bot.edit_message_text(
                            text=f"Report #{rid} Rejected ❌",
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id
                        )

                except Exception as e:
                    print(f"Reject edit failed: {e}")

                bot.answer_callback_query(call.id, "Report rejected!")

        # ================= MONTHLY APPROVE =================

        elif call.data == "approve_monthly":

            raw_text = call.message.text or call.message.caption or ""

            if "ADMIN REVIEW: Monthly Report" in raw_text:

                final_text = raw_text.split(
                    "ADMIN REVIEW: Monthly Report"
                )[1].strip()

            else:
                final_text = raw_text

            bot.send_message(
                MAIN_CHANNEL_ID,
                final_text,
                parse_mode="HTML"
            )

            bot.edit_message_text(
                "Monthly Report Posted! ✅",
                call.message.chat.id,
                call.message.message_id
            )

            bot.answer_callback_query(call.id, "Monthly report approved!")

        # ================= MONTHLY REJECT =================

        elif call.data == "reject_monthly":

            bot.edit_message_text(
                "Monthly Report Rejected ❌",
                call.message.chat.id,
                call.message.message_id
            )

            bot.answer_callback_query(call.id, "Monthly report rejected!")

    except Exception as e:
        print(f"Callback Error: {e}")

@bot.message_handler(func=lambda msg: msg.chat.type in ["group", "supergroup"])
def track_groups(msg):
    group_ids.add(msg.chat.id)

def auto_promo():
    while True:
        try:
            for gid in list(group_ids):
                try:
                    markup = InlineKeyboardMarkup()
                    
                    # Pehla button (Callback ke liye)
                    btn1 = InlineKeyboardButton("Submit Report", callback_data="create")
                    
                    # Dusra button (Link ke liye jo aapne manga)
                    btn2 = InlineKeyboardButton("Visit Channel", url="https://t.me/FraudsWatchlist")
                    
                    # Dono buttons ko add karna
                    markup.add(btn1)
                    markup.add(btn2)

                    bot.send_message(
                        gid,
                        "<b>🌟 Keep your community safe!\n"
                        "with @FraudsWatchlistBOT</b>\n\n"
                        "<b>Report scammers and verify users easily.</b>",
                        parse_mode="HTML",
                        reply_markup=markup
                    )

                    time.sleep(1)

                except Exception as e:
                    print(f"[PROMO ERROR] {gid} -> {e}")

            print("Promo sent to all groups ✅")

        except Exception as e:
            print("AUTO PROMO LOOP ERROR:", e)

        # 1 ghante ka wait
        time.sleep(3600)

if __name__ == "__main__":

    print("Bot started...")

    while True:

        try:

            bot.infinity_polling(
                timeout=10,
                long_polling_timeout=5
            )

        except Exception as e:

            print("POLLING ERROR:", e)

            time.sleep(5)