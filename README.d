import os
import logging
import json
import telebot
from telebot import types

# === НАСТРОЙКИ ===
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8053539881:AAGHeW2pkFr1fJGgS3X-YpxYw3YqLDQ1bzo")
ADMIN_IDS = [6257985367, 8011661823]
SCRIPT_FILE = "/data/scripts.json"  # ДЛЯ ХОСТИНГА
CHANNEL = "@RBX_ScriptHub"

bot = telebot.TeleBot(BOT_TOKEN)

# === БАЗА ДАННЫХ ===
def load_scripts():
    try:
        with open(SCRIPT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_scripts(scripts):
    with open(SCRIPT_FILE, 'w', encoding='utf-8') as f:
        json.dump(scripts, f, ensure_ascii=False, indent=2)

def add_script(name, code, uid, uname):
    scripts = load_scripts()
    sid = str(len(scripts) + 1)
    scripts[sid] = {
        "name": name,
        "code": code,
        "author_id": uid,
        "author_name": uname,
        "uses": 0
    }
    save_scripts(scripts)
    return sid

def get_script(sid):
    return load_scripts().get(str(sid))

def inc_uses(sid):
    scripts = load_scripts()
    if str(sid) in scripts:
        scripts[str(sid)]["uses"] += 1
        save_scripts(scripts)

# === КОМАНДЫ ===
@bot.message_handler(commands=['start'])
def start_cmd(message):
    uid = message.from_user.id
    
    if len(message.text.split()) > 1 and message.text.split()[1].startswith('script_'):
        sid = message.text.split()[1].replace('script_', '')
        script = get_script(sid)
        
        if script:
            inc_uses(sid)
            bot.reply_to(message, 
                f"🎮 <b>{script['name']}</b>\n\n"
                f"👤 Автор: {script['author_name']}\n"
                f"📥 Скачан: {script['uses']+1} раз\n\n"
                f"<code>{script['code']}</code>\n\n"
                f"👇 Скопируй код выше\n"
                f"💬 Канал: {CHANNEL}",
                parse_mode='HTML'
            )
        else:
            bot.reply_to(message, "❌ Скрипт не найден")
        return
    
    if uid in ADMIN_IDS:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➕ Добавить скрипт", callback_data="add"))
        markup.add(types.InlineKeyboardButton("📋 Список скриптов", callback_data="list"))
        
        bot.reply_to(message,
            f"🤖 <b>ScriptRoblox Bot</b>\n"
            f"Твой ID: <code>{uid}</code>\n\n"
            f"<b>Команды:</b>\n"
            f"/add - Добавить скрипт\n"
            f"/list - Показать все скрипты\n"
            f"/myid - Показать ID\n\n"
            f"<b>Формат добавления:</b>\n"
            f"Название|Описание|Код\n\n"
            f"📢 Канал: {CHANNEL}",
            parse_mode='HTML',
            reply_markup=markup
        )
    else:
        bot.reply_to(message, f"👋 Я бот для скриптов Roblox!\nПерейди по ссылке из канала {CHANNEL}")

@bot.message_handler(commands=['add'])
def add_cmd(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Нет прав!")
        return
    
    bot.reply_to(message,
        "📝 <b>Отправь скрипт в формате:</b>\n\n"
        "<code>Название|Описание|Код</code>\n\n"
        "<b>Пример:</b>\n"
        "Fly Hack|Полет|loadstring(game:HttpGet(...))()\n\n"
        f"📢 Скрипт появится в канале: {CHANNEL}",
        parse_mode='HTML'
    )

@bot.message_handler(commands=['list'])
def list_cmd(message):
    uid = message.from_user.id
    if uid not in ADMIN_IDS:
        bot.reply_to(message, "❌ Нет прав!")
        return
    
    scripts = load_scripts()
    if not scripts:
        bot.reply_to(message, "📭 Нет скриптов")
        return
    
    text = f"📋 <b>Все скрипты для {CHANNEL}:</b>\n\n"
    for sid, data in scripts.items():
        url = f"https://t.me/{bot.get_me().username}?start=script_{sid}"
        text += f"🆔 {sid}: <b>{data['name']}</b>\n"
        text += f"👤 {data['author_name']}\n"
        text += f"📥 {data['uses']} скачиваний\n"
        text += f"🔗 <code>{url}</code>\n"
        text += "─" * 20 + "\n"
    
    bot.reply_to(message, text, parse_mode='HTML')

@bot.message_handler(commands=['myid'])
def myid_cmd(message):
    bot.reply_to(message, f"🆔 Твой ID: <code>{message.from_user.id}</code>\n📢 Канал: {CHANNEL}", parse_mode='HTML')

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    uid = message.from_user.id
    if uid not in ADMIN_IDS:
        return
    
    text = message.text
    if '|' in text and text.count('|') >= 2:
        parts = text.split('|', 2)
        name = parts[0].strip()
        desc = parts[1].strip()
        code = parts[2].strip()
        
        sid = add_script(name, code, uid, message.from_user.first_name)
        url = f"https://t.me/{bot.get_me().username}?start=script_{sid}"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔗 Ссылка на скрипт", url=url))
        markup.add(types.InlineKeyboardButton(f"📢 Перейти в {CHANNEL}", url=f"https://t.me/{CHANNEL.replace('@', '')}"))
        
        bot.reply_to(message,
            f"✅ <b>Скрипт добавлен!</b>\n\n"
            f"🏷 ID: {sid}\n"
            f"🔗 <code>{url}</code>\n\n"
            f"👇 <b>Используй эту ссылку в посте канала</b>\n"
            f"📢 Канал: {CHANNEL}",
            parse_mode='HTML',
            reply_markup=markup
        )

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == "add":
        if call.from_user.id in ADMIN_IDS:
            bot.edit_message_text(
                f"📝 <b>Отправь скрипт в формате:</b>\n\n"
                f"<code>Название|Описание|Код</code>\n\n"
                f"📢 Для канала: {CHANNEL}",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML'
            )
        else:
            bot.answer_callback_query(call.id, "❌ Нет прав!")
    
    elif call.data == "list":
        if call.from_user.id in ADMIN_IDS:
            scripts = load_scripts()
            if not scripts:
                bot.answer_callback_query(call.id, "📭 Нет скриптов")
                return
            
            text = f"📋 <b>Все скрипты для {CHANNEL}:</b>\n\n"
            for sid, data in scripts.items():
                url = f"https://t.me/{bot.get_me().username}?start=script_{sid}"
                text += f"🆔 {sid}: <b>{data['name']}</b>\n"
                text += f"👤 {data['author_name']}\n"
                text += f"📥 {data['uses']} скачиваний\n"
                text += f"🔗 <code>{url}</code>\n"
                text += "─" * 20 + "\n"
            
            bot.send_message(
                call.message.chat.id,
                text,
                parse_mode='HTML'
            )
            bot.answer_callback_query(call.id, "✅ Список отправлен!")
        else:
            bot.answer_callback_query(call.id, "❌ Нет прав!")

# === ЗАПУСК ===
print(f"""
╔══════════════════════════╗
║   ScriptRoblox Bot v3.0  ║
║   Для хостинга           ║
║   Канал: {CHANNEL}       ║
╚══════════════════════════╝
""")

print(f"✅ Бот запущен для {CHANNEL}!")
print("📝 Команды: /add /list /myid /start")
bot.infinity_polling()
