import os
import json
import telebot
from telebot import types

# === НАСТРОЙКИ ===
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8053539881:AAGHeW2pkFr1fJGgS3X-YpxYw3YqLDQ1bzo")
ADMIN_IDS = [6257985367, 8011661823]
CHANNEL = "@RBX_ScriptHub"

# === ПУТЬ К БАЗЕ ДАННЫХ ===
# Для хостинга используем текущую директорию
SCRIPT_FILE = "scripts.json"

# Автоматически создаём файл если его нет
if not os.path.exists(SCRIPT_FILE):
    with open(SCRIPT_FILE, 'w', encoding='utf-8') as f:
        json.dump({}, f, ensure_ascii=False, indent=2)
    print(f"✅ Файл {SCRIPT_FILE} создан")

bot = telebot.TeleBot(BOT_TOKEN)

# === БАЗА ДАННЫХ ===
def load_scripts():
    try:
        with open(SCRIPT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            print(f"📊 Загружено {len(data)} скриптов")
            return data
    except Exception as e:
        print(f"⚠️ Ошибка загрузки БД: {e}")
        # Если файл повреждён, создаём новый
        with open(SCRIPT_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f)
        return {}

def save_scripts(scripts):
    try:
        with open(SCRIPT_FILE, 'w', encoding='utf-8') as f:
            json.dump(scripts, f, ensure_ascii=False, indent=2)
        print(f"💾 БД сохранена ({len(scripts)} скриптов)")
        return True
    except Exception as e:
        print(f"❌ Ошибка сохранения БД: {e}")
        return False

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
    
    if save_scripts(scripts):
        print(f"✅ Скрипт '{name[:20]}...' добавлен с ID {sid}")
        return sid
    else:
        print(f"❌ Ошибка добавления скрипта")
        return None

def get_script(sid):
    scripts = load_scripts()
    return scripts.get(str(sid))

def inc_uses(sid):
    scripts = load_scripts()
    sid_str = str(sid)
    if sid_str in scripts:
        scripts[sid_str]["uses"] += 1
        save_scripts(scripts)
        print(f"📈 Счётчик скрипта {sid} увеличен")

# === КОМАНДЫ ===
@bot.message_handler(commands=['start'])
def start_cmd(message):
    uid = message.from_user.id
    print(f"🚀 /start от {uid}")
    
    # Если пришла ссылка на скрипт
    if len(message.text.split()) > 1 and message.text.split()[1].startswith('script_'):
        sid = message.text.split()[1].replace('script_', '')
        print(f"🔗 Запрос скрипта {sid} от {uid}")
        
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
            print(f"✅ Скрипт {sid} отправлен пользователю {uid}")
        else:
            bot.reply_to(message, "❌ Скрипт не найден")
            print(f"❌ Скрипт {sid} не найден")
        return
    
    # Обычный старт
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
        print(f"👑 Админ {uid} вошёл в систему")
    else:
        bot.reply_to(message, f"👋 Я бот для скриптов Roblox!\nПерейди по ссылке из канала {CHANNEL}")
        print(f"👤 Пользователь {uid} запустил бота")

@bot.message_handler(commands=['add'])
def add_cmd(message):
    uid = message.from_user.id
    print(f"📝 /add от {uid}")
    
    if uid not in ADMIN_IDS:
        bot.reply_to(message, "❌ Нет прав!")
        print(f"❌ У {uid} нет прав на добавление")
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
    print(f"📋 /list от {uid}")
    
    if uid not in ADMIN_IDS:
        bot.reply_to(message, "❌ Нет прав!")
        return
    
    scripts = load_scripts()
    if not scripts:
        bot.reply_to(message, "📭 Нет скриптов")
        print(f"📭 База данных пуста")
        return
    
    text = f"📋 <b>Все скрипты для {CHANNEL}:</b> ({len(scripts)} шт.)\n\n"
    for sid, data in scripts.items():
        url = f"https://t.me/{bot.get_me().username}?start=script_{sid}"
        text += f"🆔 {sid}: <b>{data['name']}</b>\n"
        text += f"👤 {data['author_name']}\n"
        text += f"📥 {data['uses']} скачиваний\n"
        text += f"🔗 <code>{url}</code>\n"
        text += "─" * 25 + "\n"
    
    bot.reply_to(message, text, parse_mode='HTML')
    print(f"✅ Список из {len(scripts)} скриптов отправлен")

@bot.message_handler(commands=['myid'])
def myid_cmd(message):
    uid = message.from_user.id
    bot.reply_to(message, f"🆔 Твой ID: <code>{uid}</code>\n📢 Канал: {CHANNEL}", parse_mode='HTML')
    print(f"🆔 ID запрошен: {uid}")

@bot.message_handler(commands=['stats'])
def stats_cmd(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    scripts = load_scripts()
    total_uses = sum(script['uses'] for script in scripts.values())
    
    bot.reply_to(message,
        f"📊 <b>Статистика бота:</b>\n\n"
        f"📁 Всего скриптов: {len(scripts)}\n"
        f"📥 Всего скачиваний: {total_uses}\n"
        f"💾 Файл БД: {SCRIPT_FILE}\n"
        f"📢 Канал: {CHANNEL}",
        parse_mode='HTML'
    )

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    uid = message.from_user.id
    text = message.text
    
    print(f"📨 Сообщение от {uid}: {text[:50]}...")
    
    if uid not in ADMIN_IDS:
        return
    
    if '|' in text and text.count('|') >= 2:
        parts = text.split('|', 2)
        name = parts[0].strip()
        desc = parts[1].strip()
        code = parts[2].strip()
        
        print(f"➕ Добавление скрипта '{name}' от {uid}")
        
        sid = add_script(name, code, uid, message.from_user.first_name)
        
        if sid:
            url = f"https://t.me/{bot.get_me().username}?start=script_{sid}"
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔗 Ссылка на скрипт", url=url))
            markup.add(types.InlineKeyboardButton(f"📢 {CHANNEL}", url=f"https://t.me/{CHANNEL.replace('@', '')}"))
            
            bot.reply_to(message,
                f"✅ <b>Скрипт добавлен!</b>\n\n"
                f"🏷 ID: {sid}\n"
                f"🔗 <code>{url}</code>\n\n"
                f"👇 <b>Используй эту ссылку в посте канала</b>\n"
                f"📢 Канал: {CHANNEL}",
                parse_mode='HTML',
                reply_markup=markup
            )
            print(f"✅ Скрипт {sid} успешно добавлен")
        else:
            bot.reply_to(message, "❌ Ошибка при сохранении скрипта!")
            print(f"❌ Ошибка добавления скрипта")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    uid = call.from_user.id
    print(f"🔘 Callback от {uid}: {call.data}")
    
    if call.data == "add":
        if uid in ADMIN_IDS:
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
        if uid in ADMIN_IDS:
            scripts = load_scripts()
            if not scripts:
                bot.answer_callback_query(call.id, "📭 Нет скриптов")
                return
            
            text = f"📋 <b>Все скрипты для {CHANNEL}:</b> ({len(scripts)} шт.)\n\n"
            for sid, data in scripts.items():
                url = f"https://t.me/{bot.get_me().username}?start=script_{sid}"
                text += f"🆔 {sid}: <b>{data['name']}</b>\n"
                text += f"👤 {data['author_name']}\n"
                text += f"📥 {data['uses']} скачиваний\n"
                text += f"🔗 <code>{url}</code>\n"
                text += "─" * 25 + "\n"
            
            bot.send_message(call.message.chat.id, text, parse_mode='HTML')
            bot.answer_callback_query(call.id, "✅ Список отправлен!")
        else:
            bot.answer_callback_query(call.id, "❌ Нет прав!")

# === ЗАПУСК ===
print("=" * 50)
print("🤖 ScriptRoblox Bot v4.0")
print("📍 Для хостинга (исправлена БД)")
print(f"📢 Канал: {CHANNEL}")
print(f"🔑 Админы: {ADMIN_IDS}")
print(f"💾 Файл БД: {SCRIPT_FILE}")
print("=" * 50)

# Проверяем доступность файла
try:
    with open(SCRIPT_FILE, 'r') as f:
        print("✅ Файл БД доступен для чтения")
except:
    print("⚠️ Файл БД будет создан при первой записи")

print("✅ Бот запущен и готов к работе!")
print("📝 Команды: /add /list /myid /stats /start")
print("=" * 50)

bot.infinity_polling()
