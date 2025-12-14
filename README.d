import os
import json
import telebot
from telebot import types

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8053539881:AAGHeW2pkFr1fJGgS3X-YpxYw3YqLDQ1bzo")
ADMIN_IDS = [6257985367, 8011661823]
CHANNEL = "@RBX_ScriptHub"
DB_FILE = "scripts.json"  # Файл базы данных

bot = telebot.TeleBot(BOT_TOKEN)

# ================= БАЗА ДАННЫХ =================
def load_scripts():
    """Загружает скрипты из файла"""
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"📁 Загружено {len(data)} скриптов")
                return data
        else:
            # Создаём пустой файл если его нет
            with open(DB_FILE, 'w', encoding='utf-8') as f:
                json.dump({}, f)
            print("📁 Создан новый файл БД")
            return {}
    except Exception as e:
        print(f"⚠️ Ошибка загрузки БД: {e}")
        return {}

def save_scripts(scripts):
    """Сохраняет скрипты в файл"""
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(scripts, f, ensure_ascii=False, indent=2)
        print(f"💾 Сохранено {len(scripts)} скриптов")
        return True
    except Exception as e:
        print(f"❌ Ошибка сохранения БД: {e}")
        return False

def add_script(name, code, uid, uname):
    """Добавляет новый скрипт"""
    scripts = load_scripts()
    
    # Находим следующий ID
    if scripts:
        next_id = str(max(int(k) for k in scripts.keys()) + 1)
    else:
        next_id = "1"
    
    scripts[next_id] = {
        "name": name,
        "code": code,
        "author_id": uid,
        "author_name": uname,
        "uses": 0
    }
    
    if save_scripts(scripts):
        print(f"✅ Добавлен скрипт ID {next_id}: {name[:30]}")
        return next_id
    return None

def get_script(sid):
    """Получает скрипт по ID"""
    scripts = load_scripts()
    return scripts.get(str(sid))

def inc_uses(sid):
    """Увеличивает счётчик скачиваний"""
    scripts = load_scripts()
    sid_str = str(sid)
    
    if sid_str in scripts:
        scripts[sid_str]["uses"] += 1
        save_scripts(scripts)
        print(f"📥 Скрипт {sid} скачан (всего: {scripts[sid_str]['uses']})")

# ================= ПРОВЕРКА ПОДПИСКИ =================
def check_subscription(user_id):
    """Проверяет подписку на канал"""
    try:
        chat_member = bot.get_chat_member(chat_id=CHANNEL, user_id=user_id)
        if chat_member.status in ['member', 'administrator', 'creator']:
            return True
        return False
    except Exception as e:
        print(f"⚠️ Ошибка проверки подписки: {e}")
        # Если бот не админ в канале - пропускаем проверку
        return True

# ================= КОМАНДЫ =================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    
    # Если пришла ссылка на скрипт
    if len(message.text.split()) > 1 and message.text.split()[1].startswith('script_'):
        script_id = message.text.split()[1].replace('script_', '')
        
        # Проверяем подписку для обычных пользователей
        if not check_subscription(user_id) and user_id not in ADMIN_IDS:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📢 Подписаться на канал", url=f"https://t.me/{CHANNEL.replace('@', '')}"))
            markup.add(types.InlineKeyboardButton("✅ Я подписался", callback_data=f"check_{script_id}"))
            
            bot.reply_to(message,
                f"⚠️ <b>Доступ ограничен!</b>\n\n"
                f"Чтобы получить скрипт, нужно подписаться на канал:\n"
                f"{CHANNEL}\n\n"
                f"Подпишись и нажми кнопку ниже 👇",
                parse_mode='HTML',
                reply_markup=markup
            )
            return
        
        # Выдаём скрипт
        script = get_script(script_id)
        if script:
            inc_uses(script_id)
            bot.reply_to(message,
                f"🎮 <b>{script['name']}</b>\n\n"
                f"👤 Автор: {script['author_name']}\n"
                f"📥 Скачан: {script['uses']} раз\n\n"
                f"<code>{script['code']}</code>\n\n"
                f"👇 Скопируй код выше\n"
                f"💬 Канал: {CHANNEL}",
                parse_mode='HTML'
            )
        else:
            bot.reply_to(message, "❌ Скрипт не найден")
        return
    
    # Обычный старт
    if user_id in ADMIN_IDS:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➕ Добавить скрипт", callback_data="add"))
        markup.add(types.InlineKeyboardButton("📋 Список скриптов", callback_data="list"))
        
        bot.reply_to(message,
            f"🤖 <b>ScriptRoblox Bot</b>\n"
            f"Твой ID: <code>{user_id}</code>\n\n"
            f"<b>Команды:</b>\n"
            f"/add - Добавить скрипт\n"
            f"/list - Список скриптов\n\n"
            f"<b>Формат добавления:</b>\n"
            f"Название|Описание|Код\n\n"
            f"📢 Канал: {CHANNEL}",
            parse_mode='HTML',
            reply_markup=markup
        )
    else:
        if check_subscription(user_id):
            bot.reply_to(message,
                f"👋 <b>Привет!</b>\n\n"
                f"Ты подписан на {CHANNEL} и можешь получать скрипты.\n"
                f"Используй ссылки из постов канала!",
                parse_mode='HTML'
            )
        else:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📢 Подписаться на канал", url=f"https://t.me/{CHANNEL.replace('@', '')}"))
            
            bot.reply_to(message,
                f"👋 <b>Привет!</b>\n\n"
                f"Это бот для скриптов Roblox от канала {CHANNEL}\n\n"
                f"Чтобы получать скрипты, подпишись на канал 👇",
                parse_mode='HTML',
                reply_markup=markup
            )

@bot.message_handler(commands=['add'])
def add_cmd(message):
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Нет прав!")
        return
    
    bot.reply_to(message,
        "📝 <b>Отправь скрипт в формате:</b>\n\n"
        "<code>Название|Описание|Код</code>\n\n"
        "<b>Пример:</b>\n"
        "Fly Hack|Полет|loadstring(game:HttpGet(...))()",
        parse_mode='HTML'
    )

@bot.message_handler(commands=['list'])
def list_cmd(message):
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Нет прав!")
        return
    
    scripts = load_scripts()
    if not scripts:
        bot.reply_to(message, "📭 Нет скриптов")
        return
    
    text = f"📋 <b>Скрипты ({len(scripts)} шт.):</b>\n\n"
    for sid, data in scripts.items():
        url = f"https://t.me/{bot.get_me().username}?start=script_{sid}"
        text += f"🆔 <b>{sid}</b>: {data['name']}\n"
        text += f"   👤 {data['author_name']} | 📥 {data['uses']}\n"
        text += f"   🔗 {url}\n\n"
    
    bot.reply_to(message, text, parse_mode='HTML')

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    user_id = message.from_user.id
    text = message.text
    
    if user_id not in ADMIN_IDS:
        return
    
    if '|' in text and text.count('|') >= 2:
        parts = text.split('|', 2)
        name = parts[0].strip()
        desc = parts[1].strip()
        code = parts[2].strip()
        
        script_id = add_script(name, code, user_id, message.from_user.first_name)
        
        if script_id:
            url = f"https://t.me/{bot.get_me().username}?start=script_{script_id}"
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔗 Ссылка на скрипт", url=url))
            
            bot.reply_to(message,
                f"✅ <b>Скрипт добавлен!</b>\n\n"
                f"🏷 ID: {script_id}\n"
                f"🔗 <code>{url}</code>\n\n"
                f"Используй эту ссылку в посте канала",
                parse_mode='HTML',
                reply_markup=markup
            )

# ================= ОБРАБОТКА КНОПОК =================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    
    # Кнопка "Я подписался" для получения скрипта
    if call.data.startswith("check_"):
        script_id = call.data.replace("check_", "")
        
        if check_subscription(user_id) or user_id in ADMIN_IDS:
            script = get_script(script_id)
            if script:
                inc_uses(script_id)
                bot.delete_message(call.message.chat.id, call.message.message_id)
                
                bot.send_message(call.message.chat.id,
                    f"🎮 <b>{script['name']}</b>\n\n"
                    f"<code>{script['code']}</code>\n\n"
                    f"👇 Скопируй код",
                    parse_mode='HTML'
                )
                bot.answer_callback_query(call.id, "✅ Скрипт отправлен!")
            else:
                bot.answer_callback_query(call.id, "❌ Скрипт не найден")
        else:
            bot.answer_callback_query(call.id, "❌ Ты ещё не подписан!")
    
    # Кнопка "Добавить скрипт" для админов
    elif call.data == "add":
        if user_id in ADMIN_IDS:
            bot.edit_message_text(
                "📝 <b>Отправь скрипт в формате:</b>\n\n"
                "<code>Название|Описание|Код</code>",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML'
            )
    
    # Кнопка "Список скриптов" для админов
    elif call.data == "list":
        if user_id in ADMIN_IDS:
            scripts = load_scripts()
            if not scripts:
                bot.answer_callback_query(call.id, "📭 Нет скриптов")
                return
            
            text = f"📋 <b>Скрипты ({len(scripts)} шт.):</b>\n\n"
            for sid, data in scripts.items():
                url = f"https://t.me/{bot.get_me().username}?start=script_{sid}"
                text += f"🆔 <b>{sid}</b>: {data['name']}\n"
                text += f"   👤 {data['author_name']} | 📥 {data['uses']}\n"
                text += f"   🔗 {url}\n\n"
            
            bot.send_message(call.message.chat.id, text, parse_mode='HTML')
            bot.answer_callback_query(call.id, "✅ Список отправлен!")

# ================= ЗАПУСК =================
print("=" * 50)
print("🤖 ScriptRoblox Bot")
print(f"📢 Канал: {CHANNEL}")
print(f"👑 Админы: {ADMIN_IDS}")
print(f"💾 Файл БД: {DB_FILE}")
print("=" * 50)

# Проверяем наличие файла БД
if not os.path.exists(DB_FILE):
    with open(DB_FILE, 'w') as f:
        json.dump({}, f)
    print("✅ Создан файл базы данных")
else:
    scripts = load_scripts()
    print(f"✅ Загружено {len(scripts)} скриптов")

print("✅ Бот запущен и готов к работе!")
print("=" * 50)

bot.infinity_polling()
