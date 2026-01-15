from telethon import TelegramClient, events, Button
import logging
from datetime import datetime, timedelta
import sqlite3
import asyncio
import time
import random
import re
import hashlib
import uuid
import requests
from telethon.tl.types import ChatBannedRights
from collections import defaultdict

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

API_ID = '27231812'
API_HASH = '59d6d299a99f9bb97fcbf5645d9d91e9'
BOT_TOKEN = '8502910736:AAFQKj8DJMhbUUASonk6bOAbgFefvhFh878'
ADMINS = [262511724]
OWNER_ID = [262511724]
APPEAL_CHAT_ID = -1003516817505
LOG_CHANNEL = 'https://t.me/+cnym32Oi-mJiMGNi'

user_states = {}
checks_count = 0
joined_users_cache = set()
last_check_time = {}
user_message_count = defaultdict(list)
admin_cooldowns = {}
guarantor_cooldowns = {}
muted_users = {}
last_sell_command_time = {}

main_buttons = [
    [Button.text("🎭 Профиль", resize=True)],
    [Button.text("👥 Состав базы", resize=True), Button.text("🔰 Проверенные пользователи", resize=True)],
    [Button.text("📊 Статистика базы", resize=True), Button.text("🚫 Слить скаммера!", resize=True)],
    [Button.text("🔓 Премиум", resize=True), Button.text("❓ Частые вопросы", resize=True)],
    [Button.text("🔗 Проверить ссылку", resize=True)]
]

ROLES = {
    0: {"name": "Нет в базе 📝", "preview_url": "https://imgfy.ru/ib/NS5ly0KvlGnJ7TH_1768319364.jpg", "scam_chance": 31},
    1: {"name": "Гарант 🛡️", "preview_url": "https://imgfy.ru/ib/1GWpjFVMTDoAb8Q_1768319364.jpg", "scam_chance": 1},
    2: {"name": "Возможно скамер ⚠️", "preview_url": "https://imgfy.ru/ib/vgyGQVxXgTlD4su_1768319364.jpg", "scam_chance": 65},
    3: {"name": "Скамер ❌", "preview_url": "https://imgfy.ru/ib/YT6lXofT8fHsnA4_1768319364.jpg", "scam_chance": 99},
    4: {"name": "Петух 🐓", "preview_url": "https://imgfy.ru/ib/qF7jT8qDILL06Ni_1768319901.jpg", "scam_chance": 45},
    5: {"name": "Подозрение на скам ⚠️", "preview_url": "https://imgfy.ru/ib/fdnOeaUX2htvdkm_1768319365.jpg", "scam_chance": 51},
    6: {"name": "Стажёр 🎓", "preview_url": "https://imgfy.ru/ib/3ub4rh7JxOE3kno_1768319365.jpg", "scam_chance": 20},
    7: {"name": "Админ 👮", "preview_url": "https://imgfy.ru/ib/8vPp8tINWVPyYuE_1768319364.jpg", "scam_chance": 15},
    8: {"name": "Директор 👔", "preview_url": "https://imgfy.ru/ib/59y4upESFCONO2x_1768319364.jpg", "scam_chance": 10},
    9: {"name": "Президент 👑", "preview_url": "https://imgfy.ru/ib/6O81I764EZvEFFe_1768319364.jpg", "scam_chance": 5},
    10: {"name": "Создатель ⭐", "preview_url": "https://imgfy.ru/ib/HXkVyyIJl2xJ5l3_1768319364.jpg", "scam_chance": 1},
    11: {"name": "Кодер 💻", "preview_url": "https://i.ibb.co/pjYvHgP2/IMG-20250830-171539-780.jpg", "scam_chance": 3},
    12: {"name": "Проверен гарантом ✅", "preview_url": "https://imgfy.ru/ib/fDocPi2gjwsztYh_1768319365.jpg", "scam_chance": 5},
    13: {"name": "Айдош⭐", "preview_url": "https://i.ibb.co/xtQPhT16/image.jpg", "scam_chance": 20}
}

class Database:
    def __init__(self, db_name='Ice.db'):
        self.conn = sqlite3.connect(db_name, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self.lock = asyncio.Lock()
        self.create_tables()
    
    def create_tables(self):
        tables = [
            '''CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, username TEXT, role_id INTEGER DEFAULT 0,
                check_count INTEGER DEFAULT 0, country TEXT, channel TEXT, custom_photo TEXT,
                custom_photo_url TEXT, premium_points INTEGER DEFAULT 0, description TEXT,
                scammers_count INTEGER DEFAULT 0, scammers_slept INTEGER DEFAULT 0,
                warnings INTEGER DEFAULT 0, role TEXT, custom_status TEXT, granted_by_id INTEGER,
                curator_id INTEGER, allowance INTEGER DEFAULT 0
            )''',
            '''CREATE TABLE IF NOT EXISTS premium_users (
                user_id INTEGER PRIMARY KEY, expiry_date TEXT NOT NULL
            )''',
            '''CREATE TABLE IF NOT EXISTS checks (
                check_id INTEGER PRIMARY KEY AUTOINCREMENT, checker_id INTEGER, target_id INTEGER,
                check_date TEXT, description TEXT
            )''',
            '''CREATE TABLE IF NOT EXISTS scammers (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE, reason TEXT,
                reported_by TEXT, description TEXT, reporter_id INTEGER, scammer_id INTEGER,
                extra_info TEXT, unique_id VARCHAR(255)
            )''',
            '''CREATE TABLE IF NOT EXISTS statistics (total_messages INTEGER DEFAULT 0)''',
            '''CREATE TABLE IF NOT EXISTS reasons (user_id INTEGER PRIMARY KEY, reason TEXT)''',
            '''CREATE TABLE IF NOT EXISTS trainees (id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, email TEXT NOT NULL UNIQUE)''',
            '''CREATE TABLE IF NOT EXISTS messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, content TEXT
            )''',
            '''CREATE TABLE IF NOT EXISTS trust (
                user_id INTEGER PRIMARY KEY, granted_by INTEGER, grant_date TEXT
            )'''
        ]
        
        for table in tables:
            self.cursor.execute(table)
        self.cursor.execute('INSERT OR IGNORE INTO statistics (total_messages) VALUES (0)')
        self.conn.commit()
    
    def user_exists(self, user_id):
        self.cursor.execute("SELECT COUNT(*) FROM users WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone()[0] > 0
    
    def add_user(self, user_id, username, role_id=0):
        try:
            self.cursor.execute('INSERT OR IGNORE INTO users (user_id, username, role_id) VALUES (?, ?, ?)', (user_id, username, role_id))
            self.conn.commit()
        except Exception as e:
            print(f"Error adding user: {e}")
            pass
    
    def get_user_role(self, user_id):
        self.cursor.execute('SELECT role_id FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 0
    
    def update_user(self, user_id, country=None, channel=None):
        if country: self.cursor.execute('UPDATE users SET country = ? WHERE user_id = ?', (country, user_id))
        if channel: self.cursor.execute('UPDATE users SET channel = ? WHERE user_id = ?', (channel, user_id))
        self.conn.commit()
    
    def get_user_custom_photo_url(self, user_id):
        self.cursor.execute('SELECT custom_photo_url FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else None
    
    def get_granted_by(self, user_id):
        self.cursor.execute("SELECT granted_by_id FROM users WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else None
    
    def add_premium(self, user_id, expiry_date):
        try:
            self.cursor.execute('INSERT INTO premium_users (user_id, expiry_date) VALUES (?, ?)', (user_id, expiry_date))
            self.conn.commit()
        except: pass
    
    def is_premium_user(self, user_id):
        self.cursor.execute('SELECT expiry_date FROM premium_users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else None
    
    def increment_check_count(self, user_id):
        try:
            if not self.user_exists(user_id):
                self.cursor.execute('INSERT INTO users (user_id, check_count) VALUES (?, ?)', (user_id, 0))
            self.cursor.execute('UPDATE users SET check_count = check_count + 1 WHERE user_id = ?', (user_id,))
            self.conn.commit()
        except: pass
    
    def get_check_count(self, user_id):
        self.cursor.execute('SELECT check_count FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 0
    
    def update_warnings(self, user_id):
        self.cursor.execute('UPDATE users SET warnings = warnings + 1 WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    def get_warnings_count(self, user_id):
        self.cursor.execute('SELECT warnings FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 0
    
    def reset_warnings(self, user_id):
        self.cursor.execute('UPDATE users SET warnings = 0 WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    def add_scammer(self, scammer_id, reason, reported_by, description, unique_id):
        try:
            self.cursor.execute('''
                INSERT INTO scammers (user_id, reason, reported_by, description, scammer_id, unique_id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (scammer_id, reason, reported_by, description, scammer_id, unique_id))
            self.conn.commit()
            return True
        except: return False
    
    def is_scammer(self, user_id):
        self.cursor.execute("SELECT * FROM scammers WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone() is not None
    
    def get_user(self, user_id):
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return self.cursor.fetchone()
    
    def update_role(self, user_id, role_id, granted_by_id=None):
        try:
            self.cursor.execute('UPDATE users SET role_id = ? WHERE user_id = ?', (role_id, user_id))
            if granted_by_id:
                self.cursor.execute('UPDATE users SET granted_by_id = ? WHERE user_id = ?', (granted_by_id, user_id))
            self.conn.commit()
            return True
        except: return False
    
    def get_user_description(self, user_id):
        self.cursor.execute('SELECT description FROM scammers WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else "Описание отсутствует"
    
    def increment_scammers_count(self, user_id):
        self.cursor.execute("UPDATE users SET scammers_slept = scammers_slept + 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()
    
    def get_user_scammers_slept(self, user_id):
        self.cursor.execute('SELECT scammers_slept FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 0
    
    def update_user_scammers_slept(self, user_id, new_count):
        self.cursor.execute('UPDATE users SET scammers_slept = ? WHERE user_id = ?', (new_count, user_id))
        self.conn.commit()
    
    def remove_scammer_status(self, user_id):
        try:
            self.cursor.execute("DELETE FROM scammers WHERE user_id = ?", (user_id,))
            self.cursor.execute("UPDATE users SET role_id = 0 WHERE user_id = ?", (user_id,))
            self.conn.commit()
            return True
        except: return False
    
    def add_grant(self, user_id, granted_by_id):
        try:
            self.cursor.execute('INSERT INTO trust (user_id, granted_by, grant_date) VALUES (?, ?, ?)',
                               (user_id, granted_by_id, datetime.now().isoformat()))
            self.conn.commit()
        except: pass
    
    def add_premium_points(self, user_id, points):
        self.cursor.execute('UPDATE users SET premium_points = premium_points + ? WHERE user_id = ?', (points, user_id))
        self.conn.commit()
    
    def get_premium_points(self, user_id):
        self.cursor.execute('SELECT premium_points FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 0
    
    def add_check(self, checker_id, target_id):
        try:
            self.cursor.execute('INSERT INTO checks (checker_id, target_id, check_date) VALUES (?, ?, ?)',
                               (checker_id, target_id, datetime.now().isoformat()))
            self.conn.commit()
        except: pass
    
    def update_total_messages(self, count):
        self.cursor.execute('UPDATE statistics SET total_messages = total_messages + ?', (count,))
        self.conn.commit()
    
    def get_total_messages(self):
        self.cursor.execute('SELECT total_messages FROM statistics')
        result = self.cursor.fetchone()
        return result[0] if result else 0
    
    def add_or_update_premium_user(self, user_id, expiry_date):
        try:
            self.cursor.execute('''INSERT OR REPLACE INTO premium_users (user_id, expiry_date) VALUES (?, ?)''',
                               (user_id, expiry_date))
            self.conn.commit()
        except: pass
    
    def get_premium_expiry(self, user_id):
        self.cursor.execute('SELECT expiry_date FROM premium_users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else None
    
    def remove_premium(self, user_id):
        self.cursor.execute('DELETE FROM premium_users WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    async def __aenter__(self):
        await self.lock.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.lock.release()
    
    def close(self):
        try: self.conn.close()
        except: pass

bot = TelegramClient('sosot.session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
db = Database()

async def send_response(event, response_text, buttons=None):
    if buttons: await event.respond(response_text, buttons=buttons, parse_mode='md')
    else: await event.respond(response_text, parse_mode='md')

async def get_user_profile_response(event, user, user_data):
    user_id = user.id
    role_id = db.get_user_role(user_id)
    
    country = user_data[5].strip() if user_data and len(user_data) > 5 and user_data[5] else "❓"
    channel = user_data[6].strip() if user_data and len(user_data) > 6 and user_data[6] else "❓"
    description = db.get_user_description(user_id) or "Нет описания"
    checks_count = db.get_check_count(user_id)
    scammers_slept = db.get_user_scammers_slept(user_id)
    custom_image_url = db.get_user_custom_photo_url(user_id)
    current_time = datetime.now().strftime("%d.%m.%Y")
    warnings_count = db.get_warnings_count(user_id)
    granted_by_id = db.get_granted_by(user.id)
    
    granted_by_username = "Неизвестный гарант"
    if granted_by_id:
        try:
            granted_by_user = await bot.get_entity(granted_by_id)
            granted_by_username = granted_by_user.username if granted_by_user.username else granted_by_user.first_name
        except: pass
    
    role_configs = {
        0: {"template": "не найден в базе. Риск скама: **44%**", "extra": ""},
        12: {"template": f"Проверен(а) гарантом | [ {granted_by_username} ](tg://user?id={granted_by_id}) ✅", "extra": ""},
        1: {"template": "Гарант", "extra": ""},
        10: {"template": "Владелец", "extra": ""},
        9: {"template": "Президент", "extra": f"[⚠] Выговоры: {warnings_count} "},
        4: {"template": "Петух", "extra": f"📚 Описание: {description}\n\n"},
        3: {"template": "Скаммер", "extra": f"📚 Описание: {description}\n\n"},
        7: {"template": "Админ", "extra": f"[⚠] Выговоры: {warnings_count} "},
        5: {"template": "Подозрения На Скам", "extra": f"📚 Описание: {description}\n\n"},
        2: {"template": "Возможно скаммер", "extra": f"📚 Описание: {description}\n\n"},
        6: {"template": "Стажер", "extra": f"[⚠] Выговоры: {warnings_count}\n[📣] Канал: {channel}\n\n"},
        8: {"template": "Директор", "extra": f"[⚠] Выговоры: {warnings_count}\n[📣] Канал: {channel}\n\n"},
        11: {"template": "Кодер", "extra": f"[⚠] Выговоры: {warnings_count}\n[📣] Канал: {channel}\n\n"},
        13: {"template": "Айдош", "extra": f"[⚠] Выговоры: {warnings_count}\n[📣] Канал: {channel}\n\n"}
    }
    
    config = role_configs.get(role_id, {"template": "Неизвестно", "extra": ""})
    preview_url = custom_image_url if custom_image_url else ROLES[role_id]['preview_url']
    
    message_text = f"[👤][ {user.first_name} ](tg://user?id={user_id}) #id{user_id} [⠀]({preview_url})\n\n"
    message_text += f"[❌] Статус: {config['template']}\n"
    message_text += config['extra']
    message_text += f"[📍] Регион: {country}\n[🚫] Разоблачено скаммеров: {scammers_slept}\n\n"
    message_text += f"[📅] Дата: {current_time} | 🔎Проверок: {checks_count}\n"
    
    buttons = [
        [Button.url("🎧 Профиль", f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}"),
         Button.inline("⚖️ Аппеляция", f"appeal_{user_id}")],
        [Button.inline("🚫 Слить скаммера", f"report_instruction_{user_id}")]
    ]
    
    if role_id in [2, 3, 4, 5]:
        buttons.append([Button.inline("🚫 Вынести из базы", f"remove_from_db_{user_id}")])
    
    return message_text, buttons

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.respond(
        "👋 Добро пожаловать в infinity!\n\n[⠀](https://i.ibb.co/q3qgMsQz/photo-2025-04-17-17-44-18.jpg)",
        buttons=main_buttons
    )
    await event.respond("Спасибо за выбор infinity нас, добавив нашего бота в чат",
        buttons=[[Button.url("💌 добавить в чат", "http://t.me/InfinityASB_bot?startgroup=newgroup&admin=manage_chat+delete_messages+restrict_members+invite_users+restrict_members+change_info+pin_messages+manage_video_chats")]])

@bot.on(events.NewMessage(pattern=r'(?i)^(чек|чек ми|чек я|чек себя|check|/check).*'))
async def check_user(event):
    user_id = event.sender_id
    loading_msg = await event.respond("🔍")
    
    if user_id in last_check_time:
        elapsed_time = time.time() - last_check_time[user_id]
        if elapsed_time < 5:
            await loading_msg.delete()
            return await send_response(event, f"пожалуйста,подождите  {5 - elapsed_time:.1f} секунд(ы)!")
    
    last_check_time[user_id] = time.time()
    await asyncio.sleep(0.5)
    
    user_to_check = None
    if event.reply_to_msg_id:
        replied = await event.get_reply_message()
        user_to_check = await event.client.get_entity(replied.sender_id)
    else:
        if "чек себя" in event.raw_text.lower() or "чек ми" in event.raw_text.lower():
            user_to_check = await event.get_sender()
        else:
            try:
                args = event.raw_text.split()[1:]
                if args and args[0].isdigit():
                    user_id_to_check = int(args[0])
                    user_data = db.get_user(user_id_to_check)
                    if user_data: user_to_check = user_data
                    else:
                        await loading_msg.delete()
                        return await send_response(event, "❌ | Пользователь не найден в базе данных.")
                elif args:
                    user_to_check = await event.client.get_entity(args[0])
            except:
                await loading_msg.delete()
                return await send_response(event, "❌ | Не удалось найти пользователя.")
    
    if user_to_check is None:
        await loading_msg.delete()
        return await send_response(event, "❌ | Не удалось определить пользователя.")
    
    user_data = db.get_user(user_to_check.id)
    async with db:
        db.increment_check_count(user_to_check.id)
        global checks_count
        checks_count += 1
        
        response = await get_user_profile_response(event, user_to_check, user_data)
        if isinstance(response, tuple):
            message_text, buttons = response
        else:
            message_text = response
            buttons = []
        
        try:
            await send_response(event, message_text[:4096] if len(message_text) > 4096 else message_text, buttons)
        except: pass
        
        if db.is_premium_user(user_id) and event.raw_text.lower() in ('чек', '/check'):
            await bot.send_message(user_id, f'🔍 Пользователь [{user_to_check.first_name}](tg://user?id={user_id}) проверял вас в боте!',
                                  buttons=Button.inline("↩Скрыть", b"hide_message"))
    
    try: await loading_msg.delete()
    except: pass

@bot.on(events.NewMessage(pattern="👥 Состав базы"))
async def members_menu(event):
    if not event.is_private: return
    buttons = [[Button.text("✅ Гаранты базы", resize=True)], [Button.text("👨‍🎓 Волонтёры базы", resize=True)], [Button.text("↩ Назад", resize=True)]]
    await event.respond("👥 **Меню состава базы**\n\nВыберите категорию участников для просмотра:", buttons=buttons, parse_mode='md')

@bot.on(events.NewMessage(pattern="✅ Гаранты базы"))
async def list_garants(event):
    if not event.is_private: return
    try: garants = [row[0] for row in db.cursor.execute('SELECT user_id FROM users WHERE role_id = 1')]
    except: garants = []
    if not garants: await event.respond("На данный момент Гарантов нету ⛔"); return
    text = f"""💢 Актуальный список гарантов infinity\n━━━━━━━━━━━━━━\n• Всего: {len(garants)}\n━━━━━━━━━━━━━━\n💡 Если хотите стать гарантом, пройдите набор!\n[⠀](https://i.ibb.co/rGBBGyng/photo-2025-04-17-17-44-20.jpg)"""
    buttons = []
    for uid in garants:
        try:
            user = await bot.get_entity(uid)
            buttons.append([Button.inline(f"🛡️ {user.first_name}", f"check_{uid}")])
        except: continue
    await event.respond(text, buttons=buttons, parse_mode='md', link_preview=True)

@bot.on(events.NewMessage(pattern="👨‍🎓 Волонтёры базы"))
async def list_volunteers(event):
    if not event.is_private: return
    volunteers = []
    for role_id in [6, 7, 8, 9, 10]:
        volunteers.extend([row[0] for row in db.cursor.execute('SELECT user_id FROM users WHERE role_id = ?', (role_id,))])
    if not volunteers: await event.respond("На данный момент Волонтёров нету ⛔"); return
    text = f"""🤝 Актуальный список волонтёров infinity\n━━━━━━━━━━━━━━\n• Всего: {len(volunteers)}\n━━━━━━━━━━━━━━\n💡 Если вы хотите стать волонтёром базы, просто пройдите набор!\n[⠀](https://i.ibb.co/rGKnW46r/photo-2025-04-17-17-44-19.jpg)"""
    buttons = []
    for uid in volunteers:
        try:
            user = await bot.get_entity(uid)
            role_id = db.get_user_role(uid)
            role_name = ROLES[role_id]["name"]
            buttons.append([Button.inline(f"{role_name} {user.first_name}", f"check_{uid}")])
        except: continue
    await event.respond(text, buttons=buttons, parse_mode='md', link_preview=True)

@bot.on(events.NewMessage(pattern="🔰 Проверенные пользователи"))
async def list_verified_users(event):
    if not event.is_private: return
    verified_users = [row[0] for row in db.cursor.execute('SELECT user_id FROM users WHERE role_id = 12')]
    if not verified_users: await event.respond("На данный момент проверенных пользователей нет ⛔"); return
    text = "📊 Вот наш список проверенных пользователей:\n"
    buttons = []
    for uid in verified_users:
        try:
            user = await bot.get_entity(uid)
            buttons.append([Button.inline(f"✅ {user.first_name}", f"check_{uid}")])
        except: continue
    await event.respond(text, buttons=buttons, parse_mode='md', link_preview=True)

@bot.on(events.NewMessage(pattern="📊 Статистика базы"))
async def statistics(event):
    if not event.is_private: return
    total_checks = db.cursor.execute('SELECT SUM(check_count) FROM users').fetchone()[0] or 0
    scammers_count = db.cursor.execute('SELECT COUNT(*) FROM scammers').fetchone()[0]
    total_users = db.cursor.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    roles_stats = {
        'admins': db.cursor.execute('SELECT COUNT(*) FROM users WHERE role_id = 7').fetchone()[0],
        'guarantors': db.cursor.execute('SELECT COUNT(*) FROM users WHERE role_id = 1').fetchone()[0],
        'verified': db.cursor.execute('SELECT COUNT(*) FROM users WHERE role_id = 12').fetchone()[0],
        'trainees': db.cursor.execute('SELECT COUNT(*) FROM users WHERE role_id = 6').fetchone()[0]
    }
    text = f"""🔍 Статистика:\n[⠀](https://i.ibb.co/dwfVKmMH/photo-2025-04-17-17-44-19-2.jpg)\n🚫 Скаммеров: {scammers_count}\n👥 Пользователей: {total_users}\n⚖️ Админов: {roles_stats['admins']}\n💎 Гарантов: {roles_stats['guarantors']}\n✅ Проверенных: {roles_stats['verified']}\n👨‍🎓 Стажеров: {roles_stats['trainees']}\n🔎 Всего проверок: {total_checks}\n⏳ Последняя проверка: {datetime.now().strftime('%d.%m.%Y %H:%M')}"""
    buttons = [[Button.inline("🏆 Топ Стажеров", b"top_trainees")], [Button.inline("😎 Топ Активных", b"top_day")], [Button.url("🎇 Наша База", 'https://t.me/infinityANTIscam')]]
    stat_message = await event.respond(text, parse_mode='md', link_preview=True, buttons=buttons)
    bot.stat_message_id = stat_message.id

@bot.on(events.NewMessage(pattern="🚫 Слить скаммера!"))
async def report_scammer(event):
    if not event.is_private: return
    keyboard = Button.url("🚨 Отправить жалобу", "https://t.me/infinityantiscam")
    await event.respond("""🔥 Вы хотите слить скаммера? 🔥\n\n⚡️ Лучшее решение:\n• Нажмите кнопку \"🚨 Отправить жалобу\"\n• Наш персонал примет меры\n\n🔒 Как избежать скама?:\n1. ✅ Всегда проверяйте через /check\n2. ✅ Используйте гарантов\n3. ✅ Требуйте подтверждения\n4. ✅ При сомнениях - отменяйте\n\n📛 Помните: 95% скама можно избежать!\n[⠀](https://i.ibb.co/bj4g7h3y/photo-2025-04-17-17-44-19-3.jpg)""", parse_mode='md', link_preview=True, buttons=keyboard)

@bot.on(events.NewMessage(pattern="🔓 Премиум"))
async def premium_info(event):
    final_image = "https://i.ibb.co/bMbQc9c0/photo-2025-06-01-12-01-48.jpg"
    text = f"Откройте уникальные возможности: [ ](https://i.ibb.co/bMbQc9c0/photo-2025-06-01-12-01-48.jpg)\n\n• Установить кастомное фото\n• Поставить ссылку на канал\n• Получать уведомления\nВсе фишки в infinity Premium"
    buttons = [[Button.url("💰 Оплата", "https://t.me/rewylerss")], [Button.inline("↩ Скрыть", b"hide_message")]]
    await event.respond(text, buttons=buttons, parse_mode='md', link_preview=True)

@bot.on(events.NewMessage(pattern="❓ Частые вопросы"))
async def faq_handler(event):
    faq_buttons = [
        [Button.inline("Кто такой гарант?", "who_is_guarantee")],
        [Button.inline("Как найти гаранта?", "find_guarantee")],
        [Button.inline("Как стать волонтёром?", "become_volunteer")],
        [Button.inline("Как стать гарантом?", "become_guarantee")],
        [Button.inline("Как слить скаммера?", "report_scammer")],
        [Button.inline("Когда набор на админов?", "admin_recruitment")],
        [Button.inline("Можно ли купить роль в базе?", "buy_role")],
        [Button.inline("Можно ли купить снятие из базы?", "buy_removal")],
        [Button.inline("Вернуться ↩", "back_to_main")]
    ]
    await event.respond("Выберите нужный вам пункт:[⠀](https://i.ibb.co/q3bGLp9J/image.png)", buttons=faq_buttons)

@bot.on(events.CallbackQuery)
async def faq_callback_handler(event):
    callback_data = event.data.decode()
    responses = {
        "who_is_guarantee": "💁‍♂️ Кто такой гарант?\n\n[У нас есть мини-статья об этом (ТЫК)](https://telegra.ph/Kto-takoj-GARANT-05-29)",
        "find_guarantee": "💁‍♂️ Как найти гаранта?\n\nВ лс с ботом жмём кнопку 'Гаранты' или вводим /mms.\n\nБот отобразит вам проверенных людей",
        "become_volunteer": "💁‍♂️ Как стать волонтёром?\n\nСледите за информацией в новостнике базы и участвуйте в наборах.",
        "become_guarantee": "💁‍♂️ Как стать гарантом?\n\nСледите за информацией в новостнике базы и участвуйте в наборах.",
        "report_scammer": "💁‍♂️ Как слить скаммера?\n\nСлить скаммера можно в нашей группе жалоб - новостнике базы.\n- Заходите в группу и кидаете пруфы скама",
        "admin_recruitment": "💁‍♂️ Когда набор на админов?\n\nВ среднем наборы проходят 2 раза в месяц.",
        "buy_role": "НЕТ. Мы НЕ продаём админки/ роли гарантов в нашей базе. Если вы хотите поддержать нашу базу - /premium.",
        "buy_removal": "НЕТ. Мы НЕ удаляем пользователей. Наша цель - быть надёжным и честным источником информации.",
        "back_to_main": ""
    }
    if callback_data in responses and responses[callback_data]:
        await event.respond(responses[callback_data], buttons=Button.inline("↩ Назад", "back_to_main"))

@bot.on(events.NewMessage(pattern="🔗 Проверить ссылку"))
async def check_link(event):
    buttons = [[Button.inline("1: Роблокс", b"check_roblox")], [Button.inline("2: Сайт", b"check_site")], [Button.inline("3: Проверить на стиллер/логер", b"check_logger")]]
    await event.respond("Выберите тип ссылки:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"check_roblox"))
async def handle_roblox_link(event):
    buttons = [[Button.inline("1: Роблокс профиль", b"roblox_profile")], [Button.inline("2: Пригласительная ссылка", b"invite_link")], [Button.inline("3: Ссылка на Роблокс", b"roblox_link")]]
    await event.respond("Выберите пункт:", buttons=buttons)

@bot.on(events.NewMessage(pattern="↩ Назад"))
async def back_to_main(event):
    if not event.is_private: return
    await event.respond("Главное меню:", buttons=main_buttons)

@bot.on(events.NewMessage(pattern="🎭 Профиль"))
async def my_profile(event):
    if not event.is_private:
        await event.delete()
        return
    
    user_id = event.sender_id
    user = await event.get_sender()
    
    # Если пользователя нет в базе - добавляем
    if not db.user_exists(user_id):
        db.add_user(user_id, user.username, 0)
    
    user_data = db.get_user(user_id)
    if user_data is None:
        await event.respond("❌ Не удалось найти ваши данные в базе.")
        return
    
    role_id = db.get_user_role(user_id)
    role_info = ROLES[role_id]
    
    # Получаем данные как в функции check_soon_handler
    db.add_check(user_id, user_id)
    current_time = datetime.now()
    user_data = db.get_user(user_id)
    country = user_data[5] if user_data and user_data[5] else "Не указана"
    channel = user_data[6] if user_data and user_data[6] else None
    custom_photo = user_data[8] if user_data else None
    
    # Формируем текст как в check_soon_handler
    response = f"👤 | Пользователь: [{user.first_name}](tg://user/{user.id})\n\n🔍 | ID: `{user.id}`\n\n🤗 | Роль в базе: {role_info['name']}\n\n🌍 | Страна: {country}\n\n📢 | Канал: {channel}\n\n⚖ | Шанс скама: {role_info['scam_chance']}%\n\n📅 {current_time.strftime('%d.%m.%Y')} | 🔍 {db.get_check_count(user_id)}\n\n[Просмотреть медиа]({custom_photo if custom_photo else role_info['preview_url']})"
    
    buttons = [
        [Button.url("👤 Профиль", f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}"), Button.url("🔗 Ссылка", f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}")],
        [Button.url("⚠️ Слить скаммера", "https://t.me/infinityantiscam"), Button.url("⚖️ Аппеляция", "https://t.me/infinityAPPEALS")]
    ]
    
    await event.respond(response, buttons=buttons, parse_mode='md')

@bot.on(events.CallbackQuery(pattern='check_soon'))
async def check_soon_handler(event):
    try:
        user = await event.client.get_entity(event.sender_id)
        user_id = user.id
        
        # Если пользователя нет в базе - добавляем
        if not db.user_exists(user_id):
            db.add_user(user_id, user.username, 0)
        
        current_role_id = db.get_user_role(user_id)
        db.add_check(user_id, user_id)
        current_time = datetime.now()
        role_info = ROLES[current_role_id]
        user_data = db.get_user(user_id)
        country = user_data[5] if user_data and user_data[5] else "Не указана"
        channel = user_data[6] if user_data and user_data[6] else None
        custom_photo = user_data[8] if user_data and user_data[8] else None
        
        response = f"👤 | Пользователь: [{user.first_name}](tg://user/{user.id})\n\n🔍 | ID: `{user.id}`\n\n🤗 | Роль в базе: {role_info['name']}\n\n🌍 | Страна: {country}\n\n📢 | Канал: {channel}\n\n⚖ | Шанс скама: {role_info['scam_chance']}%\n\n📅 {current_time.strftime('%d.%m.%Y')} | 🔍 {db.get_check_count(user_id)}\n\n[Просмотреть медиа]({custom_photo if custom_photo else role_info['preview_url']})"
        
        buttons = [
            [Button.url("👤 Профиль", f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}"), Button.url("🔗 Ссылка", f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}")],
            [Button.url("⚠️ Слить скаммера", "https://t.me/infinityantiscam"), Button.url("⚖️ Аппеляция", "https://t.me/infinityAPPEALS")]
        ]
        
        await event.respond(response, buttons=buttons, parse_mode='md')
        await event.answer()
    except Exception as e:
        await event.answer("❌ Произошла ошибка при обработке запроса", alert=True)

@bot.on(events.CallbackQuery(pattern='themes_soon'))
async def themes_handler(event):
    status_photos = {
        6: ["https://cdn.streamable.com/video/mp4/z1j4w6.mp4", "https://i.ibb.co/jPQpWgg3/temp-5173733679-1248.jpg"],
        8: ["https://i.ibb.co/Z6qKqwvY/temp-5173733679.jpg", "https://i.ibb.co/XfYFmf8n/temp-5173733679-1178.jpg"],
        7: ["https://i.ibb.co/VWYdQrwK/temp-5173733679-1310.jpg", "https://i.ibb.co/hRNMk3Pg/temp-5173733679-1295.jpg"],
        9: ["https://i.ibb.co/d4jHKRZC/temp-5173733679-1311.jpg", "https://i.ibb.co/pjYcnsHk/temp-5173733679-1182.jpg"],
        0: ["https://i.ibb.co/qYfWnnvY/temp-5173733679-1176.jpg", "https://i.ibb.co/23G4pXk6/temp-5173733679.jpg"]
    }
    
    user_id = event.sender_id
    role_id = db.get_user_role(user_id)
    photos = status_photos.get(role_id, [])
    
    if not photos:
        await event.respond("📸 У вас нет доступных фотографий для выбора.")
        return
    
    current_index = 0
    
    async def send_photo(index):
        if 0 <= index < len(photos):
            await event.respond(f"📸 Выберите фото для статуса:\n\n[❤]({photos[index]})", buttons=[
                [Button.inline("◀", f"photo_prev_{index}"), Button.inline("Выбрать!", f"select_photo_{index}"), Button.inline("▶", f"photo_next_{index}")]
            ], link_preview=True)
    
    await send_photo(current_index)

@bot.on(events.CallbackQuery(pattern=r'select_photo_(\d+)'))
async def select_photo_handler(event):
    index = int(event.pattern_match.group(1))
    user_id = event.sender_id
    role_id = db.get_user_role(user_id)
    status_photos = {
        6: ["https://cdn.streamable.com/video/mp4/z1j4w6.mp4", "https://i.ibb.co/jPQpWgg3/temp-5173733679-1248.jpg"],
        8: ["https://i.ibb.co/Z6qKqwvY/temp-5173733679.jpg", "https://i.ibb.co/XfYFmf8n/temp-5173733679-1178.jpg"],
        7: ["https://i.ibb.co/VWYdQrwK/temp-5173733679-1310.jpg", "https://i.ibb.co/hRNMk3Pg/temp-5173733679-1295.jpg"],
        9: ["https://i.ibb.co/d4jHKRZC/temp-5173733679-1311.jpg", "https://i.ibb.co/pjYcnsHk/temp-5173733679-1182.jpg"],
        0: ["https://i.ibb.co/qYfWnnvY/temp-5173733679-1176.jpg", "https://i.ibb.co/23G4pXk6/temp-5173733679.jpg"]
    }
    photos = status_photos.get(role_id, [])
    if 0 <= index < len(photos):
        db.cursor.execute('UPDATE users SET custom_photo_url = ? WHERE user_id = ?', (photos[index], user_id))
        db.conn.commit()
        await event.respond("✅ Новое фото успешно установлено в статус!")

@bot.on(events.CallbackQuery(pattern=r'photo_prev_(\d+)'))
async def photo_prev_handler(event):
    index = int(event.pattern_match.group(1)) - 1
    user_id = event.sender_id
    role_id = db.get_user_role(user_id)
    status_photos = {
        6: ["https://cdn.streamable.com/video/mp4/z1j4w6.mp4", "https://i.ibb.co/jPQpWgg3/temp-5173733679-1248.jpg"],
        8: ["https://i.ibb.co/Z6qKqwvY/temp-5173733679.jpg", "https://i.ibb.co/XfYFmf8n/temp-5173733679-1178.jpg"],
        7: ["https://i.ibb.co/VWYdQrwK/temp-5173733679-1310.jpg", "https://i.ibb.co/hRNMk3Pg/temp-5173733679-1295.jpg"],
        9: ["https://i.ibb.co/d4jHKRZC/temp-5173733679-1311.jpg", "https://i.ibb.co/pjYcnsHk/temp-5173733679-1182.jpg"],
        0: ["https://i.ibb.co/qYfWnnvY/temp-5173733679-1176.jpg", "https://i.ibb.co/23G4pXk6/temp-5173733679.jpg"]
    }
    photos = status_photos.get(role_id, [])
    if 0 <= index < len(photos):
        await event.respond(f"📸 Выберите фото для статуса:\n\n[❤]({photos[index]})", buttons=[
            [Button.inline("◀", f"photo_prev_{index}"), Button.inline("Выбрать!", f"select_photo_{index}"), Button.inline("▶", f"photo_next_{index}")]
        ], link_preview=True)

@bot.on(events.CallbackQuery(pattern=r'photo_next_(\d+)'))
async def photo_next_handler(event):
    index = int(event.pattern_match.group(1)) + 1
    user_id = event.sender_id
    role_id = db.get_user_role(user_id)
    status_photos = {
        6: ["https://cdn.streamable.com/video/mp4/z1j4w6.mp4", "https://i.ibb.co/jPQpWgg3/temp-5173733679-1248.jpg"],
        8: ["https://i.ibb.co/Z6qKqwvY/temp-5173733679.jpg", "https://i.ibb.co/XfYFmf8n/temp-5173733679-1178.jpg"],
        7: ["https://i.ibb.co/VWYdQrwK/temp-5173733679-1310.jpg", "https://i.ibb.co/hRNMk3Pg/temp-5173733679-1295.jpg"],
        9: ["https://i.ibb.co/d4jHKRZC/temp-5173733679-1311.jpg", "https://i.ibb.co/pjYcnsHk/temp-5173733679-1182.jpg"],
        0: ["https://i.ibb.co/qYfWnnvY/temp-5173733679-1176.jpg", "https://i.ibb.co/23G4pXk6/temp-5173733679.jpg"]
    }
    photos = status_photos.get(role_id, [])
    if 0 <= index < len(photos):
        await event.respond(f"📸 Выберите фото для статуса:\n\n[❤]({photos[index]})", buttons=[
            [Button.inline("◀", f"photo_prev_{index}"), Button.inline("Выбрать!", f"select_photo_{index}"), Button.inline("▶", f"photo_next_{index}")]
        ], link_preview=True)

@bot.on(events.CallbackQuery(pattern='custom_soon'))
async def custom_soon_handler(event):
    user_id = event.sender_id
    if not db.is_premium_user(user_id):
        await event.answer("❌ У вас нет премиум статуса! Для установки Кастом картинки приобретите премиум.", alert=True)
        return
    
    await event.respond("Отправьте изображение или видео")
    
    @bot.on(events.NewMessage(from_users=user_id))
    async def media_handler(media_event):
        if media_event.photo or media_event.video:
            try:
                media_path = await bot.download_media(media_event.photo or media_event.video)
                if media_event.photo:
                    with open(media_path, "rb") as image_file:
                        files = {"image": image_file}
                        params = {"key": "cb21b904cc405cdfc05731896bc29c64"}
                        response = requests.post("https://api.imgbb.com/1/upload", params=params, files=files)
                        data = response.json()
                    import os
                    os.remove(media_path)
                    if data.get("success") and "data" in data and "url" in data["data"]:
                        image_url = data["data"]["url"]
                        db.cursor.execute('UPDATE users SET custom_photo_url = ? WHERE user_id = ?', (image_url, user_id))
                        db.conn.commit()
                        await media_event.reply(f"✅ Кастомное изображение успешно установлено в статус!\nСсылка: {image_url}", parse_mode='md')
                elif media_event.video:
                    video_url = f"https://t.me/your_bot_name?start=video_{media_event.video.id}"
                    db.cursor.execute('UPDATE users SET custom_photo_url = ? WHERE user_id = ?', (video_url, user_id))
                    db.conn.commit()
                    await media_event.reply(f"✅ Кастомное видео успешно установлено в статус!\nСсылка: {video_url}", parse_mode='md')
            except Exception as e:
                await media_event.reply(f"❌ Произошла ошибка: {str(e)}")
        else:
            await media_event.reply("❌ Пожалуйста, отправьте изображение или видео.")
        bot.remove_event_handler(media_handler)

@bot.on(events.CallbackQuery(pattern='remove_custom'))
async def remove_custom_handler(event):
    user_id = event.sender_id
    db.cursor.execute('UPDATE users SET custom_photo_url = NULL WHERE user_id = ?', (user_id,))
    db.conn.commit()
    await event.answer("✅ Кастомное изображение успешно удалено.")
    await back_to_profile_handler(event)

@bot.on(events.CallbackQuery(pattern='channel_soon'))
async def channel_soon_handler(event):
    user_id = event.sender_id
    if not db.is_premium_user(user_id):
        await event.answer("❌ У вас нет премиум статуса! Для установки канала приобретите премиум.", alert=True)
        return
    
    await event.respond("Отправьте username канала (например, @channelname)")
    
    @bot.on(events.NewMessage(from_users=user_id))
    async def channel_handler(channel_event):
        channel_name = channel_event.text.strip()
        if not channel_name.startswith('@'):
            await channel_event.reply("❌ Имя канала должно начинаться с @")
        elif len(channel_name) > 32:
            await channel_event.reply("❌ Имя канала слишком длинное (макс. 32 символа)")
        else:
            db.update_user(channel_event.sender_id, channel=channel_name)
            await channel_event.reply(f"✅ Канал {channel_name} успешно сохранен!")
        bot.remove_event_handler(channel_handler)

@bot.on(events.CallbackQuery(pattern='country_soon'))
async def country_soon_handler(event):
    countries = [
        "США 🇺🇸", "Канада 🇨🇦", "Мексика 🇲🇽", "Бразилия 🇧🇷",
        "Аргентина 🇦🇷", "Великобритания 🇬🇧", "Франция 🇫🇷",
        "Германия 🇩🇪", "Италия 🇮🇹", "Испания 🇪🇸", "Китай 🇨🇳",
        "Япония 🇯🇵", "Австралия 🇦🇺", "Индия 🇮🇳", "Россия 🇷🇺",
        "Южноафриканская Республика 🇿🇦", "Египет 🇪🇬", "ОАЭ 🇦🇪",
        "Турция 🇹🇷", "Греция 🇬🇷", "Швеция 🇸🇪", "Норвегия 🇳🇴",
        "Финляндия 🇫🇮", "Дания 🇩🇰", "Польша 🇵🇱", "Чехия 🇨🇿",
        "Австрия 🇦🇹", "Швейцария 🇨🇭", "Нидерланды 🇳🇱", "Бельгия 🇧🇪",
        "Ирландия 🇮🇪", "Португалия 🇵🇹", "Румыния 🇷🇴", "Словакия 🇸🇰",
        "Словения 🇸🇮", "Хорватия 🇭🇷", "Латвия 🇱🇻", "Литва 🇱🇹",
        "Эстония 🇪🇪", "Мальта 🇲🇹", "Кипр 🇨🇾", "Исландия 🇮🇸"
    ]
    
    buttons = [Button.inline(country, f"set_country_{i}") for i, country in enumerate(countries)]
    await event.respond("🌍 Выберите страну, выбраная вами страна будет стоять у вас в профиле!", buttons=[buttons[i:i + 3] for i in range(0, len(buttons), 3)])

@bot.on(events.CallbackQuery(pattern=r'set_country_(\d+)'))
async def set_country_handler(event):
    country_idx = int(event.data.decode().split('_')[2])
    countries = [
        "США 🇺🇸", "Канада 🇨🇦", "Мексика 🇲🇽", "Бразилия 🇧🇷",
        "Аргентина 🇦🇷", "Великобритания 🇬🇧", "Франция 🇫🇷",
        "Германия 🇩🇪", "Италия 🇮🇹", "Испания 🇪🇸", "Китай 🇨🇳",
        "Япония 🇯🇵", "Австралия 🇦🇺", "Индия 🇮🇳", "Россия 🇷🇺",
        "Южноафриканская Республика 🇿🇦", "Египет 🇪🇬", "ОАЭ 🇦🇪",
        "Турция 🇹🇷", "Греция 🇬🇷", "Швеция 🇸🇪", "Норвегия 🇳🇴",
        "Финляндия 🇫🇮", "Дания 🇩🇰", "Польша 🇵🇱", "Чехия 🇨🇿",
        "Австрия 🇦🇹", "Швейцария 🇨🇭", "Нидерланды 🇳🇱", "Бельгия 🇧🇪",
        "Ирландия 🇮🇪", "Португалия 🇵🇹", "Румыния 🇷🇴", "Словакия 🇸🇰",
        "Словения 🇸🇮", "Хорватия 🇭🇷", "Латвия 🇱🇻", "Литва 🇱🇹",
        "Эстония 🇪🇪", "Мальта 🇲🇹", "Кипр 🇨🇾", "Исландия 🇮🇸"
    ]
    
    if 0 <= country_idx < len(countries):
        country = countries[country_idx]
        db.update_user(event.sender_id, country=country)
        await event.respond(f"✅ Страна установлена: {country}")

@bot.on(events.CallbackQuery(pattern='help_soon'))
async def help_soon_handler(event):
    help_text = """🤖 **Команды бота:**\n\n📋 **Проверка пользователей:**\n• `Чек [юзернейм/ID]` - проверить пользователя\n• `Чек` (ответом на сообщение) - проверить пользователя\n• `Чек ми/я/себя` - проверить себя\n\n👮‍♂️ **Выдача ролей (только для админов):**\n• `+роль` (ответом на сообщение)\n• `-роль` (снять роль)\n\n📊 **Другие команды:**\n• `/profile` - ваш профиль\n• `/stats` - статистика бота\n• `/report` - пожаловаться на скамера"""
    await event.respond(help_text, buttons=[Button.inline("« Назад", "back_to_profile")])

@bot.on(events.CallbackQuery(pattern='back_to_profile'))
async def back_to_profile_handler(event):
    user = await event.get_sender()
    user_id = user.id
    
    # Если пользователя нет в базе - добавляем
    if not db.user_exists(user_id):
        db.add_user(user_id, user.username, 0)
    
    role = db.get_user_role(user_id)
    role_info = ROLES[role]
    user_data = db.get_user(user_id)
    custom_photo = user_data[8] if user_data else None
    preview_url = custom_photo if custom_photo else role_info['preview_url']
    checks_count = db.get_check_count(user_id)
    custom_button_text = "🎆 Снять кастомное изображение" if custom_photo else "🎆 Установить кастомку"
    custom_callback_data = "remove_custom" if custom_photo else "custom_soon"
    
    keyboard = [
        [Button.inline("🔎 Проверить себя", "check_soon"), Button.inline("🎨 Тема проверки", "themes_soon")],
        [Button.inline("📢 Канал", "channel_soon"), Button.inline("🌍 Страна", "country_soon")],
        [Button.inline(custom_button_text, custom_callback_data)]
    ]
    
    # Текст как в check_soon_handler
    user_data = db.get_user(user_id)
    country = user_data[5] if user_data and user_data[5] else "Не указана"
    channel = user_data[6] if user_data and user_data[6] else None
    current_time = datetime.now()
    
    profile_text = f"👤 | Пользователь: [{user.first_name}](tg://user/{user.id})\n\n🔍 | ID: `{user.id}`\n\n🤗 | Роль в базе: {role_info['name']}\n\n🌍 | Страна: {country}\n\n📢 | Канал: {channel}\n\n⚖ | Шанс скама: {role_info['scam_chance']}%\n\n📅 {current_time.strftime('%d.%m.%Y')} | 🔍 {checks_count}\n\n[Просмотреть медиа]({preview_url})"
    
    await event.respond(profile_text, buttons=keyboard, parse_mode='md')

@bot.on(events.NewMessage(pattern=r'(?i)^\+спасибо'))
async def thank_command(event):
    user_id = event.sender_id
    user_role = db.get_user_role(user_id)
    allowed_roles = [6, 8, 10, 11, 9, 13]
    
    if user_role not in allowed_roles:
        return
    
    if event.reply_to_msg_id:
        reply_message = await event.get_reply_message()
        target_user_id = reply_message.sender_id
        target_user_role = db.get_user_role(target_user_id)
        
        if target_user_role in [1, 6, 8, 9, 10, 11, 13]:
            return
    
    try:
        db.increment_scammers_count(target_user_id)
        await event.respond(f"📛 пользователю с ID: {target_user_id} выдано +спасибо.\n\n📈 Спасибо, что боретесь со скамом вместе с infinity [ ] (https://i.ibb.co/HDc1Bwpr/photo-2025-04-17-17-44-20-4.jpg).\n\n☕ Если у вас есть ещё скаммеры, сообщите об этом нашим стажёрам или администраторам!")
    except:
        await event.respond("❌ Произошла ошибка при увеличении счетчика слитых скаммеров.")

@bot.on(events.NewMessage(pattern=r'(?i)^/скам|/sc|/scam'))
async def scam_command(event):
    user_id = event.sender_id
    user_role = db.get_user_role(user_id)
    allowed_roles = [6, 8, 10, 11, 9]
    
    if user_role not in allowed_roles and user_id not in OWNER_ID:
        await event.respond("❌ У вас нет прав для использования этой команды")
        return
    
    args = event.raw_text.split(maxsplit=2)
    if len(args) < 3:
        await event.respond("❌ Используйте: /скам @username/ID *причина*")
        return
    
    target = args[1]
    reason = args[2].strip('*')
    
    try:
        if target.isdigit():
            user = await event.client.get_entity(int(target))
        else:
            if target.startswith('@'):
                target = target[1:]
            user = await event.client.get_entity(target)
    except:
        await event.respond("❌ Не могу найти пользователя")
        return
    
    if db.is_scammer(user.id):
        await event.respond(f"❌ Пользователь [{user.first_name}](tg://user/{user.id}) уже находится в базе скаммеров!")
        return
    
    target_user_role = db.get_user_role(user.id)
    if target_user_role == 10:
        await event.respond("❌ Действие не допустимо, вы не можете занести владельца базы!")
        return
    
    unique_id = str(uuid.uuid4())
    db.add_user(user.id, user.username)
    success = db.add_scammer(user.id, reason, user_id, reason, unique_id)
    
    if not success:
        await event.respond(f"❌ Пользователь [{user.first_name}](tg://user/{user.id}) уже находится в базе скаммеров!")
        return
    
    buttons = [
        [Button.inline("Скамер ❌", f"mark_scammer_{user.id}_{unique_id}")],
        [Button.inline("Подозрение на скам ⚠️", f"mark_suspect_{user.id}_{unique_id}")],
        [Button.inline("Возможно скаммер ⚠️", f"mark_possible_{user.id}_{unique_id}")],
        [Button.inline("Петух 🐓", f"mark_rooster_{user.id}_{unique_id}")]
    ]
    
    await event.respond(f"⚠️ Выберите роль для пользователя {user.first_name} | 🆔 {user.id}\n\n", buttons=buttons, parse_mode='md')

@bot.on(events.CallbackQuery(pattern=r'mark_(scammer|possible|suspect|rooster)_(\d+)_(.+)'))
async def mark_user_handler(event):
    role_mapping = {'scammer': 3, 'possible': 2, 'suspect': 5, 'rooster': 4}
    role_type = event.pattern_match.group(1).decode('utf-8')
    user_id = int(event.pattern_match.group(2))
    reason = event.pattern_match.group(3).strip().decode('utf-8')
    
    current_role = db.get_user_role(user_id)
    if current_role in [2, 3, 4, 5]:
        await event.answer("❌ Этот пользователь уже находится в базе!", alert=True)
        return
    
    user_role = db.get_user_role(event.sender_id)
    if user_role not in [1, 6, 8, 10, 11, 9] and event.sender_id != OWNER_ID:
        await event.answer("⛔ У вас нет прав лол.", alert=True)
        return
    
    if not reason:
        await event.answer("❌ Причина не может быть пустой!", alert=True)
        return
    
    db.update_role(user_id, role_mapping[role_type])
    current_count = db.get_user_scammers_slept(event.sender_id)
    scammers_slept = current_count + 1
    
    if not db.update_user_scammers_slept(event.sender_id, scammers_slept):
        await event.answer("Ошибка при обновлении количества слитых скаммеров.", alert=True)
        return
    
    chat_id = event.chat_id
    await event.client.send_message(chat_id, message=f"🔥 Вы успешно занесли скаммера! | Скаммеров слито: {scammers_slept}")

@bot.on(events.CallbackQuery(pattern=r'remove_from_db_(\d+)'))
async def remove_from_db_handler(event):
    user_id = int(event.pattern_match.group(1))
    sender_role = db.get_user_role(event.sender_id)
    allowed_roles = [6, 7, 8, 9, 10, 11, 13]
    
    if sender_role not in allowed_roles:
        await event.answer("❌ У вас нет прав для выполнения этого действия!", alert=True)
        return
    
    try:
        target_user = await bot.get_entity(user_id)
        target_role = db.get_user_role(user_id)
        
        if target_role not in [2, 3, 4, 5]:
            await event.answer("❌ Этот пользователь не является скамером!", alert=True)
            return
        
        db.update_role(user_id, 0)
        db.cursor.execute('DELETE FROM scammers WHERE user_id = ?', (user_id,))
        db.conn.commit()
        admin_user = await bot.get_entity(event.sender_id)
        
        await event.answer("✅ Пользователь успешно вынесен из базы!", alert=True)
        await event.edit(f"👤 Пользователь [{target_user.first_name}](tg://user?id={user_id}) был вынесен из базы\n👮 Вынес: [{admin_user.first_name}](tg://user?id={event.sender_id})\n📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            buttons=[[Button.url("🎧 Профиль", f"https://t.me/{target_user.username}" if target_user.username else f"tg://user?id={user_id}"), Button.inline("⚖️ Аппеляция", f"appeal_{user_id}")]], parse_mode='md')
    except:
        await event.answer("❌ Произошла ошибка при выносе из базы!", alert=True)

@bot.on(events.CallbackQuery(pattern=r'appeal_(\d+)'))
async def appeal_handler(event):
    target_user_id = int(event.pattern_match.group(1))
    sender_id = event.sender_id
    user_states[sender_id] = {'appeal_target': target_user_id, 'waiting_for_appeal': True}
    
    try:
        await bot.send_message(sender_id, f"📝 Вы начали процесс апелляции на пользователя с ID {target_user_id}.\n\nПожалуйста, напишите текст вашей апелляции. Опишите подробно причины, по которым считаете, что пользователь не должен быть в базе скамеров.\n\n❌ Отправьте 'отмена' для отмены процесса.")
        await event.answer("📨 Инструкции по апелляции отправлены вам в личные сообщения", alert=True)
    except:
        await event.answer("❌ Не удалось отправить сообщение. Убедитесь, что у бота есть доступ к вашим ЛС", alert=True)

@bot.on(events.NewMessage)
async def handle_appeal_text(event):
    user_id = event.sender_id
    
    if event.is_private and user_id in user_states and user_states[user_id].get('waiting_for_appeal'):
        appeal_text = event.raw_text.strip()
        
        if appeal_text.lower() in ['отмена', 'cancel', 'отменить']:
            if user_id in user_states: del user_states[user_id]
            await event.respond("❌ Процесс апелляции отменен.")
            return
        
        if not appeal_text:
            await event.respond("❌ Текст апелляции не может быть пустым. Пожалуйста, напишите вашу апелляцию.")
            return
        
        target_user_id = user_states[user_id]['appeal_target']
        
        try:
            target_user = await bot.get_entity(target_user_id)
            sender_user = await event.get_sender()
            
            appeal_message = f"🚨 **Новая апелляция**\n\n👤 **На пользователя:** {target_user.first_name} (ID: {target_user_id})\n📝 **От пользователя:** {sender_user.first_name} (ID: {user_id})\n📄 **Текст апелляции:**\n{appeal_text}\n\n⏰ **Время подачи:** {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            
            try:
                await bot.send_message(APPEAL_CHAT_ID, appeal_message, parse_mode='md')
                await event.respond("✅ Ваша апелляция успешно отправлена на рассмотрение!\n\nМы рассмотрим ваше обращение в ближайшее время. О результате уведомим вас личным сообщением.")
            except:
                await event.respond("❌ Ошибка при отправке апелляции в группу. Пожалуйста, сообщите администраторам об ошибке.")
        except:
            await event.respond("❌ Произошла ошибка при обработке апелляции. Пожалуйста, попробуйте позже или свяжитесь с администраторами.")
        
        if user_id in user_states: del user_states[user_id]

@bot.on(events.CallbackQuery(pattern=r'report_instruction_(\d+)'))
async def report_instruction_handler(event):
    target_user_id = int(event.pattern_match.group(1))
    sender_id = event.sender_id
    
    try:
        instruction_text = """📋 **ИНСТРУКЦИЯ ПО ЗАНОСУ СКАММЕРА**\n\nЧтобы занести скаммера в базу:\n\n1. **Перейдите в группу жалоб**: @infinityantiscam\n2. **Предоставьте доказательства**:\n   • Скриншоты переписки\n   • Подтверждения платежей\n   • Любые другие материалы\n3. **Укажите данные скаммера**\n4. **Ожидайте рассмотрения** модераторами\n\n🤝 **Спасибо за помощь в борьбе со скамом!**"""
        
        await event.answer("📨 Инструкции по апелляции отправлены вам в личные сообщения", alert=True)
        await bot.send_message(sender_id, instruction_text, parse_mode='md')
        await event.answer("✅ Инструкция отправлена в ваши ЛС!", show_alert=False)
    except:
        await event.answer("❌ Включите ЛС с ботом!", alert=True)
        await event.respond("""❌ **Не удалось отправить инструкцию в ЛС**\n\n📋 **Краткая инструкция:**\n1. Перейдите в @Huntesreport\n2. Предоставьте доказательства скама\n3. Укажите данные пользователя\n4. Ожидайте рассмотрения\n\n💡 *Чтобы получать полные инструкции, разрешите боту писать вам в ЛС*""", parse_mode='md')

@bot.on(events.CallbackQuery(data=b"top_trainees"))
async def top_trainees_handler(event):
    try:
        await bot.delete_messages(event.chat_id, bot.stat_message_id)
    except: pass
    
    try:
        top_trainees = db.cursor.execute('SELECT user_id, username, scammers_slept FROM users WHERE role_id = 6 ORDER BY scammers_slept DESC LIMIT 10').fetchall()
        
        if not top_trainees:
            msg = await event.respond("📭 Список стажеров пока пуст!", buttons=Button.inline("↩Вернуться", b"return_to_stats"))
            bot.last_message_id = msg.id
            return
        
        response = "🏆 Топ 10 стажеров по слитым скаммерам:\n\n"
        for i, (user_id, username, count) in enumerate(top_trainees, 1):
            user_link = f"[{username or f'ID:{user_id}'}](tg://user?id={user_id})"
            response += f"{i}. {user_link} — 🚫 {count} скаммеров\n"
        
        msg = await event.respond(response, parse_mode='Markdown', buttons=Button.inline("↩Вернуться", b"return_to_stats"))
        bot.last_message_id = msg.id
    except:
        await event.respond(f"⚠️ Ошибка", buttons=Button.inline("↩Вернуться", b"return_to_stats"))

@bot.on(events.CallbackQuery(data=b"return_to_stats"))
async def return_to_stats_handler(event):
    try:
        await bot.delete_messages(event.chat_id, event.message_id)
        user = await event.get_sender()
        total_checks = db.cursor.execute('SELECT SUM(check_count) FROM users').fetchone()[0] or 0
        scammers_count = db.cursor.execute('SELECT COUNT(*) FROM scammers').fetchone()[0]
        total_users = db.cursor.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        roles_stats = {
            'admins': db.cursor.execute('SELECT COUNT(*) FROM users WHERE role_id = 7').fetchone()[0],
            'guarantors': db.cursor.execute('SELECT COUNT(*) FROM users WHERE role_id = 1').fetchone()[0],
            'verified': db.cursor.execute('SELECT COUNT(*) FROM users WHERE role_id = 12').fetchone()[0],
            'trainees': db.cursor.execute('SELECT COUNT(*) FROM users WHERE role_id = 6').fetchone()[0]
        }
        
        text = f"""🔍 {user.first_name}, вот текущая статистика бота:
[⠀](https://i.ibb.co/Fzpqd0K/IMG-3735.jpg)
🚫 Скаммеров в базе: {scammers_count}
👥 Пользователей бота: {total_users}

⚖️ Админов: {roles_stats['admins']}
💎 Гарантов: {roles_stats['guarantors']}
✅ Проверенных: {roles_stats['verified']}
👨‍🎓 Стажеров: {roles_stats['trainees']}

🔎 Всего проверок: {total_checks}
⏳ Последняя проверка: {datetime.now().strftime('%d.%m.%Y %H:%M')}"""
        
        buttons = [[Button.inline("🏆 Топ Стажеров", b"top_trainees")], [Button.inline("😎 Топ Активных", b"top_day")]]
        stat_message = await event.respond(text, parse_mode='md', link_preview=True, buttons=buttons)
        bot.stat_message_id = stat_message.id
    except: pass

@bot.on(events.CallbackQuery(data=b"top_day"))
async def top_day_handler(event):
    try:
        await bot.delete_messages(event.chat_id, bot.stat_message_id)
    except: pass
    
    try:
        db.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'")
        if not db.cursor.fetchone():
            msg = await event.respond("⚠️ Таблица сообщений ещё не создана. Активность не отслеживается.", buttons=Button.inline("↩Скрыть", b"hide_message"))
            bot.last_message_id = msg.id
            return
        
        top_users = db.cursor.execute('SELECT u.user_id, u.username, COUNT(m.message_id) as count FROM users u JOIN messages m ON u.user_id = m.user_id WHERE m.timestamp >= datetime(\'now\', \'-1 day\') GROUP BY u.user_id ORDER BY count DESC LIMIT 10').fetchall()
        
        if not top_users:
            msg = await event.respond("📭 Пока нет активности за последние 24 часа!", buttons=Button.inline("↩Скрыть", b"hide_message"))
            bot.last_message_id = msg.id
            return
        
        response = "😎 Топ 10 активных пользователей за 24 часа:\n\n"
        for i, (user_id, username, count) in enumerate(top_users, 1):
            user_link = f"[{username or f'ID:{user_id}'}](tg://user?id={user_id})"
            response += f"{i}. {user_link} — ✉️ {count} сообщений\n"
        
        msg = await event.respond(response, buttons=Button.inline("↩Скрыть", b"hide_message"))
        bot.last_message_id = msg.id
    except:
        await event.respond(f"⚠️ Произошла ошибка", buttons=Button.inline("↩Скрыть", b"hide_message"))

@bot.on(events.CallbackQuery(data=b"hide_message"))
async def hide_message_handler(event):
    try: await event.delete()
    except: pass

@bot.on(events.NewMessage(pattern=r'(?i)^/траст|!trust'))
async def trust_command(event):
    sender = await event.get_sender()
    
    if db.get_user_role(sender.id) not in [1, 10]:
        await event.reply("**⚠️ Отказано в доступе!**\n\n**👤 Пользователь:** [{sender.first_name}](tg://user/{sender.id})\n**📛 Причина:** Недостаточно прав\n**ℹ️ Информация:** Выдавать траст могут только гаранты и создатель\n[⠀](https://i.ibb.co/rGBBGyng/photo-2025-04-17-17-44-20.jpg)", parse_mode='md', link_preview=True)
        return
    
    target = await get_target_user(event)
    if not target: return
    
    granted_by_username = sender.username if sender.username else f"ID: {sender.id}"
    target_role = db.get_user_role(target.id)
    
    if target_role in [6, 7, 8, 9, 10, 11, 12]:
        await event.reply(f"**❌ Ошибка!**\n\n**📛 Причина:** Нельзя выдавать траст владельцу, кодеру, стажеру, гаранту, президенту, админу или директору.\n**📝 Текущая роль:** {ROLES[target_role]['name']}", parse_mode='md')
        return
    
    async with db.lock:
        user_role = db.get_user_role(target.id)
        if user_role is not None and user_role > 0:
            await event.reply(f"**❌ Ошибка!**\n\n**📛 Причина:** У пользователя уже есть роль в базе.\n**📝 Текущая роль:** {ROLES[user_role]['name']}", parse_mode='md')
            return
        
        db.update_role(target.id, 12, granted_by_id=sender.id)
        db.add_grant(target.id, sender.id)
    
    await event.reply(f"**✅ Траст успешно выдан!**\n\n**👤 Получатель:** [{target.first_name}](tg://user/{target.id})\n**👮 Выдал:** [{sender.first_name}](tg://user/{sender.id})\n💙 Репутация: Проверен(а) гарантом {granted_by_username} ✅", parse_mode='md')

async def get_target_user(event):
    if event.is_reply:
        replied = await event.get_reply_message()
        return await event.client.get_entity(replied.sender_id)
    else:
        args = event.raw_text.split()
        if len(args) < 2:
            await event.reply("**❌ Ошибка использования команды!**\n\n**✏️ Правильное использование:**\n• `/trust` (ответом на сообщение)\n• `/trust @username`\n• `/trust ID`", parse_mode='md')
            return None
        try:
            return await event.client.get_entity(args[1])
        except:
            await event.reply("**❌ Ошибка!**\n\n**📛 Причина:** Не удалось найти пользователя\n**💡 Совет:** Проверьте правильность указанного юзернейма/ID", parse_mode='md')
            return None

@bot.on(events.NewMessage(pattern=r'/untrust|/антраст|-антраст'))
async def untrust_command(event):
    sender = await event.get_sender()
    sender_role = db.get_user_role(sender.id)
    
    if sender_role != 1 and sender.id not in OWNER_ID and sender_role not in [10, 11]:
        await event.reply("**⚠️ Отказано!**\n\n**👤 Пользователь:** [{sender.first_name}](tg://user/{sender.id})\n**📛 Причина:** У тя прав нету пон?\n**ℹ️ Информация:** Снимать траст могут только гаранты, создатель и владельцы\n[⠀](https://i.ibb.co/rGBBGyng/photo-2025-04-17-17-44-20.jpg)", parse_mode='md', link_preview=True)
        return
    
    if event.is_reply:
        replied = await event.get_reply_message()
        target = await event.client.get_entity(replied.sender_id)
    else:
        args = event.raw_text.split()
        if len(args) < 2:
            await event.reply("**❌ Ошибка использования команды!**\n\n**✏️ Правильное использование:**\n• `/untrust` (ответом на сообщение)\n• `/untrust @username`\n• `/untrust ID`", parse_mode='md')
            return
        
        try:
            target = await event.client.get_entity(args[1])
        except:
            await event.reply("**❌ ну, ошибочка вышла):**\n\n**📛 Причина:** Не удалось найти пользователя\n**💡 Совет:** Дебик, правильно ник введи или айди, заебали уже честно.", parse_mode='md')
            return
    
    if db.get_user_role(target.id) != 12:
        await event.reply("**❌ Ну не плач только ошибочка получилась**\n\n**📛 Причина:** Его нет в базе даун..", parse_mode='md')
        return
    
    db.update_role(target.id, 0)
    await event.reply("**✅ Траст успешно снят!, плаки плаки ):**\n\n**👤 Пользователь:** [{target.first_name}](tg://user/{target.id})\n**👮 Снял:** [{sender.first_name}](tg://user/{sender.id})", parse_mode='md')

@bot.on(events.NewMessage(pattern=r'\+премиум'))
async def add_premium(event):
    if event.sender_id not in OWNER_ID and db.get_user_role(event.sender_id) not in [10, 11]:
        await event.reply("❌ У вас нет прав для выполнения этого действия!")
        return
    
    try:
        if event.is_reply:
            replied = await event.get_reply_message()
            target = await event.client.get_entity(replied.sender_id)
            duration = event.raw_text.split()[-1].lower()
        else:
            args = event.raw_text.split()
            if len(args) != 2:
                await event.reply("**❌ Использование:**\n`+премиум @username 1д`")
                return
            
            try:
                if args[1].isdigit():
                    target = await event.client.get_entity(int(args[1]))
                else:
                    target = await event.client.get_entity(args[1])
            except:
                await event.reply("**❌ Не удалось найти пользователя!**")
                return
        
        amount = int(duration[:-1])
        unit = duration[-1]
        
        if unit == 'м': delta = timedelta(minutes=amount); time_str = f"{amount} минут"
        elif unit == 'ч': delta = timedelta(hours=amount); time_str = f"{amount} часов"
        elif unit == 'д': delta = timedelta(days=amount); time_str = f"{amount} дней"
        elif unit == 'г': delta = timedelta(days=amount * 365); time_str = f"{amount} лет"
        else:
            await event.reply("**❌ Неверный формат времени!**")
            return
        
        expiry_date = (datetime.now() + delta).strftime("%Y-%m-%d %H:%M:%S")
        db.add_or_update_premium_user(target.id, expiry_date)
        
        try:
            await bot.send_message(target.id, "**🎉 Вам выдан премиум доступ!**", buttons=Button.url("📢 Предложка", "https://t.me/infinityantiscam"))
        except: pass
        
        await event.reply(f"**✅ Премиум успешно выдан!**\n\n**👤 Получатель:** [{target.first_name}](tg://user/{target.id})\n**⏱ Длительность:** {time_str}", buttons=[Button.inline("❌ Снять премиум", f"remove_premium_{target.id}")], parse_mode='md')
    except Exception as e:
        await event.reply(f"**❌ Ошибка:** `{str(e)}`")

@bot.on(events.NewMessage(pattern=r'-премиум'))
async def remove_premium_command(event):
    if event.sender_id not in OWNER_ID and db.get_user_role(event.sender_id) not in [10, 11]:
        await event.reply("❌ У вас нет прав для выполнения этого действия!")
        return
    
    try:
        if event.is_reply:
            replied = await event.get_reply_message()
            target = await event.client.get_entity(replied.sender_id)
        else:
            args = event.raw_text.split()
            if len(args) != 2:
                await event.reply("**❌ Использование:**\n`-премиум @username` или `-премиум ID`")
                return
            
            try:
                if args[1].isdigit():
                    target = await event.client.get_entity(int(args[1]))
                else:
                    target = await event.client.get_entity(args[1])
            except:
                await event.reply("**❌ Не удалось найти пользователя!**")
                return
        
        if db.get_premium_expiry(target.id):
            db.remove_premium(target.id)
            
            try:
                await bot.send_message(target.id, "**🕵️‍♂️ Ваш премиум статус был снят.**", buttons=Button.url("📢 Предложка", "https://t.me/infinityantiscam"))
            except: pass
            
            await event.reply(f"**✅ Премиум успешно снят!**\n\n**👤 Пользователь:** [{target.first_name}](tg://user/{target.id})", parse_mode='md')
        else:
            await event.reply("❌ У пользователя нет премиум статуса!")
    except Exception as e:
        await event.reply(f"**❌ Ошибка:** `{str(e)}`")

@bot.on(events.CallbackQuery(pattern=r'remove_premium_(\d+)'))
async def remove_premium_button(event):
    if event.sender_id not in OWNER_ID and db.get_user_role(event.sender_id) not in [10, 11]:
        await event.answer("❌ У вас нет прав для выполнения этого действия!", alert=True)
        return
    
    user_id = int(event.data.decode().split('_')[2])
    
    if db.get_premium_expiry(user_id):
        db.remove_premium(user_id)
        
        try:
            target = await event.client.get_entity(user_id)
            
            try:
                await bot.send_message(user_id, "**🕵️‍♂️ Шо те лох премиум сняли?.**", buttons=Button.url("📢 Предложка", "https://t.me/infinityantiscam"))
            except: pass
            
            await event.edit(f"**✅ Премиум успешно снят!**\n\n**👤 Пользователь:** [{target.first_name}](tg://user/{target.id})", buttons=None, parse_mode='md')
        except Exception as e:
            await event.edit(f"**❌ Ошибка:** `{str(e)}`")
    else:
        await event.answer("❌ У пользователя нет премиума!", alert=True)

@bot.on(events.ChatAction)
async def handle_chat_join(event):
    if not (event.user_joined or event.user_added): return
    user = await event.get_user()
    user_id = user.id
    if user.bot: return
    if user_id in joined_users_cache: return
    joined_users_cache.add(user_id)
    asyncio.create_task(remove_from_cache_later(user_id))
    user_role = db.get_user_role(user_id)
    image_url = "https://i.ibb.co/q3qgMsQz/photo-2025-04-17-17-44-18.jpg"
    
    if user_role == 11:
        buttons = [[Button.inline("🤗", "welcome_coder")]]
        text = f"""☕ Добро пожаловать! [{user.first_name}](tg://user?id={user.id})\n\nДобро пожаловать!!😊\n\n[🤗]({image_url})"""
        await event.respond(text, buttons=buttons, parse_mode='md', link_preview=True)
    elif user_role in [6, 7, 8, 9, 10]:
        text = f"""☕ Добро пожаловать! [{user.first_name}](tg://user?id={user.id})\n\n[🤗]({image_url})"""
        await event.respond(text, parse_mode='md', link_preview=True)
    elif user_role == 12:
        text = f"""🔥 К чату присоединился человек, проверенный гарантом Grand\n\n[🤗]({image_url})"""
        await event.respond(text, parse_mode='md', link_preview=True)
    elif user_role == 3:
        buttons = [[Button.inline("ЗАБАНИТЬ ⛔", f"ban_{user.id}")]]
        text = f"""⚠️ К чату присоединился [{user.first_name}](tg://user?id={user.id}) **Скаммер**!\n\nНе доверяйте этому человеку.\n\n[🤗]({image_url})"""
        await event.respond(text, buttons=buttons, parse_mode='md', link_preview=True)
    elif user_role in [2, 4, 5]:
        buttons = [[Button.inline("ЗАБАНИТЬ ⛔", f"ban_{user.id}")]]
        text = f"""⚠️ К чату присоединился [{user.first_name}](tg://user?id={user.id}) с высоким шансом скама!\n\nВероятность скама: {ROLES[user_role]['scam_chance']}%\n\n[🤗]({image_url})"""
        await event.respond(text, buttons=buttons, parse_mode='md', link_preview=True)
    else:
        buttons = [[Button.inline("🤗", "welcome")]]
        text = f"""👋 Добро пожаловать! [{user.first_name}](tg://user?id={user.id})\n\n[🤗](https://i.ibb.co/q3qgMsQz/photo-2025-04-17-17-44-18.jpg)"""
        await event.respond(text, buttons=buttons, parse_mode='md', link_preview=True)
    
    if user_id in muted_users:
        expiry_time = muted_users[user_id]
        if time.time() < expiry_time:
            await bot.edit_permissions(event.chat_id, user_id, view_messages=False)
        else:
            del muted_users[user_id]

async def remove_from_cache_later(user_id, delay=600):
    await asyncio.sleep(delay)
    joined_users_cache.discard(user_id)

@bot.on(events.NewMessage())
async def count_messages(event):
    global checks_count
    checks_count += 1
    db.update_total_messages(1)

@bot.on(events.NewMessage(pattern=r'(?i)^админы!$'))
async def call_admins(event):
    user_id = event.sender_id
    current_time = datetime.now()
    
    if user_id in admin_cooldowns:
        time_diff = current_time - admin_cooldowns[user_id]
        if time_diff < timedelta(hours=4):
            remaining = timedelta(hours=4) - time_diff
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            await event.respond(f"**⏳ Подождите {hours} ч. {minutes} мин. прежде чем снова вызывать админов!**")
            return
    
    admin_cooldowns[user_id] = current_time
    
    conn = sqlite3.connect('Ice.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users WHERE role_id IN (6,7,8,9,10,13)')
    admins = cursor.fetchall()
    conn.close()
    
    mentions_text = "**✅ Админы вызваны!**"
    for admin in admins:
        mentions_text += f"[\u200b](tg://user?id={admin[0]})"
        caller_username = event.sender.username
        caller_mention = f"@{caller_username}" if caller_username else event.sender.mention
        admin_message = f"**🚨 В чате пользователь {caller_mention} вызывает админов!**"
        await bot.send_message(admin[0], admin_message)
    
    await event.respond(mentions_text)

@bot.on(events.NewMessage(pattern=r'(?i)^гаранты!$'))
async def call_guarantors(event):
    user_id = event.sender_id
    current_time = datetime.now()
    
    if user_id in guarantor_cooldowns:
        time_diff = current_time - guarantor_cooldowns[user_id]
        if time_diff < timedelta(hours=1):
            remaining = timedelta(hours=1) - time_diff
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            await event.respond(f"**⏳ Подождите {hours} ч. {minutes} мин. прежде чем снова вызывать гарантов!**")
            return
    
    guarantor_cooldowns[user_id] = current_time
    
    guarantors = [row[0] for row in db.cursor.execute('SELECT user_id FROM users WHERE role_id = 1')]
    mentions_text = "**🔰 Гаранты вызваны!**"
    
    for guarantor_id in guarantors:
        mentions_text += f"[\u200b](tg://user?id={guarantor_id})"
        caller_username = event.sender.username
        caller_mention = f"@{caller_username}" if caller_username else event.sender.mention
        guarantor_message = f"**🚨 В чате пользователь {caller_mention} вызывает гарантов!**"
        await bot.send_message(guarantor_id, guarantor_message)
    
    await event.respond(mentions_text)

@bot.on(events.NewMessage(pattern=r'[+-](?:[А-Яа-я]+)(?:\s+(?:@?\w+|\d+))?'))
async def handle_role_command(event):
    user_role = db.get_user_role(event.sender_id)
    is_admin = event.sender_id in [262511724] or user_role == 10
    
    if not is_admin:
        msg = await event.reply("❌ У вас нет прав для выполнения этой команды", buttons=Button.inline("↩Скрыть", b"hide_message"))
        bot.last_message_id = msg.id
        return
    
    command_parts = event.raw_text.split()
    action = command_parts[0][0]
    role = command_parts[0][1:].lower()
    
    try:
        if len(command_parts) > 1:
            target = command_parts[1]
            if target.isdigit():
                user = await event.client.get_entity(int(target))
            else:
                if target.startswith('@'):
                    target = target[1:]
                user = await event.client.get_entity(target)
        else:
            if not event.is_reply:
                msg = await event.reply("❌ Укажите пользователя или ответьте на его сообщение", buttons=Button.inline("↩Скрыть", b"hide_message"))
                bot.last_message_id = msg.id
                return
            replied = await event.get_reply_message()
            user = await event.client.get_entity(replied.sender_id)
    except:
        msg = await event.reply("❌ Не удалось найти пользователя!", buttons=Button.inline("↩Скрыть", b"hide_message"))
        bot.last_message_id = msg.id
        return
    
    role_mapping = {
        'стажер': 6, 'админ': 7, 'директор': 8, 'президент': 9,
        'гарант': 1, 'кодер': 11, 'создатель': 10, 'айдош': 13
    }
    
    if role not in role_mapping:
        msg = await event.reply("❌ Неизвестная роль!", buttons=Button.inline("↩Скрыть", b"hide_message"))
        bot.last_message_id = msg.id
        return
    
    # Добавляем пользователя если его нет
    if not db.user_exists(user.id):
        db.add_user(user.id, user.username, 0)
    
    if action == '+':
        # Создатель и владелец могут выдавать любые роли
        if event.sender_id in [262511724] or user_role == 10:
            db.update_role(user.id, role_mapping[role])
            msg = await event.reply(f"✅ Роль {role} выдана пользователю [{user.first_name}](tg://user?id={user.id})", buttons=Button.inline("↩Скрыть", b"hide_message"))
            bot.last_message_id = msg.id
        else:
            msg = await event.reply("❌ У вас нет прав для выдачи ролей!", buttons=Button.inline("↩Скрыть", b"hide_message"))
            bot.last_message_id = msg.id
    else:
        # Для снятия роли
        if event.sender_id in [262511724] or user_role == 10:
            db.update_role(user.id, 0)
            msg = await event.reply(f"✅ Роль снята с пользователя [{user.first_name}](tg://user?id={user.id})", buttons=Button.inline("↩Скрыть", b"hide_message"))
            bot.last_message_id = msg.id
        else:
            msg = await event.reply("❌ У вас нет прав для снятия ролей!", buttons=Button.inline("↩Скрыть", b"hide_message"))
            bot.last_message_id = msg.id

@bot.on(events.NewMessage(pattern=r'(?i)^(выговор|/выговор)'))
async def warning_handler(event):
    if event.is_reply:
        replied = await event.get_reply_message()
        target_user = await event.client.get_entity(replied.sender_id)
    else:
        await event.reply("❌ Пожалуйста, используйте команду в ответ на сообщение пользователя.")
        return
    
    user_role = db.get_user_role(event.sender_id)
    
    target_user_role = db.get_user_role(target_user.id)
    if target_user_role == 10:
        await event.reply("Ты шо ахуел?, нельзя владельцу выговоры выдавать!.")
        return
    
    if user_role not in [13, 8, 9, 10]:
        await event.reply("❌ У вас нет прав для выдачи выговора.")
        return
    
    result = db.cursor.execute('SELECT warnings FROM users WHERE user_id = ?', (target_user.id,)).fetchone()
    
    if result is None:
        db.add_user(target_user.id, target_user.username, 0)
        warnings_count = 0
    else:
        warnings_count = result[0]
    
    db.update_warnings(target_user.id)
    new_warnings_count = db.cursor.execute('SELECT warnings FROM users WHERE user_id = ?', (target_user.id,)).fetchone()[0]
    
    if new_warnings_count >= 3:
        db.update_role(target_user.id, 0)
        db.reset_warnings(target_user.id)
        await event.reply(f"✅ Пользователь [{target_user.first_name}](tg://user/{target_user.id}) получил 3 выговора и теперь имеет статус 'Нет в базе'.")
    else:
        await event.reply(f"✅ Выговор выдан пользователю [{target_user.first_name}](tg://user/{target_user.id})")

@bot.on(events.NewMessage(pattern=r'(?i)^(/-выговор|снять выговор)'))
async def remove_warnings_handler(event):
    if event.is_reply:
        replied = await event.get_reply_message()
        target_user = await event.client.get_entity(replied.sender_id)
    else:
        await event.reply("❌ Пожалуйста, используйте команду в ответ на сообщение пользователя.")
        return
    
    user_role = db.get_user_role(event.sender_id)
    
    if user_role not in [13, 8, 9, 10]:
        await event.reply("❌ У вас нет прав для снятия выговоров.")
        return
    
    result = db.cursor.execute('SELECT warnings FROM users WHERE user_id = ?', (target_user.id,)).fetchone()
    if result is None:
        await event.reply("❌ Пользователь не найден в базе.")
        return
    
    warnings_count = result[0]
    
    if warnings_count <= 0:
        await event.reply(f"❌ У пользователя [{target_user.first_name}](tg://user/{target_user.id}) нет выговоров.")
        return
    
    db.cursor.execute('UPDATE users SET warnings = warnings - 1 WHERE user_id = ?', (target_user.id,))
    db.conn.commit()
    
    new_warnings_count = db.cursor.execute('SELECT warnings FROM users WHERE user_id = ?', (target_user.id,)).fetchone()[0]
    
    await event.reply(f"✅ выговор снят у пользователя [{target_user.first_name}](tg://user/{target_user.id}).")

@bot.on(events.NewMessage(pattern=r'продать (.+)'))
async def sell_command(event):
    user_id = event.sender_id
    item_to_sell = event.pattern_match.group(1)
    
    current_time = time.time()
    if user_id in last_sell_command_time:
        if current_time - last_sell_command_time[user_id] < 10:
            await event.respond("Потерпи брадок, 10 секунд не так уж и много.")
            return
    
    last_sell_command_time[user_id] = current_time
    
    if random.randint(1, 100) <= 15:
        success_texts = [
            f"ЁЁЁЁЁЁУУУУУУУУУ😎😎😎 Да ты своего {item_to_sell} продал цыганам за 5 копеек, хочешь вернуть да?, того пиздуй искать в бд неуч!",
            f"Нихуя себе какой важный хуй бумажный🎴, ты продал своего {item_to_sell} на органы! Хочешь сохранить друга\n\n Тогда Ищи в бд! Неуч блять!",
            f"О!, а куда это твой {item_to_sell} делся? Кажись его цыгани спиздили! Смотреть надо за своим {item_to_sell}, а не хуи пинать!\n\n Вы на базаре всё-таки! Всего проёбано {random.randint(1, 10)}."
        ]
        await event.respond(random.choice(success_texts))
    else:
        losses = random.randint(1, 10)
        response_texts = [
            f"БЛЯЯЯЯЯЯЯЯЯЯЯ😭😭 Ты проебал своего {item_to_sell} в казик, кажись его логи схавали.\n\nВсего ты проебал {losses}. Поищи в логах!",
            f"АХХХПАХХАХАХАПХПАХАПХ ЕБАТЬ ТЫ ЛОХ🤣🤣, Ты где-то проебал {item_to_sell} ищи в бд!\n\nВсего проёбано {losses}.",
            f"Лелелелелеле😑, тебе чё занятся нехуй? своего {item_to_sell} на базаре продавать. пиздуй ищи в логах!\n\nВсего проёбано {losses}."
        ]
        
        response_message = random.choice(response_texts)
        buttons = [[Button.inline("🔍Искать ещё раз!", f"search_again_{user_id}"), Button.inline("🤑Гойда продадим что-то?", f"sell_something_{user_id}")]]
        message = await event.respond(response_message, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=r'search_again_(\d+)'))
async def search_again_handler(event):
    user_id = int(event.pattern_match.group(1))
    await event.answer("Да мне лень работать чё-то🥱🥱", alert=False)

@bot.on(events.CallbackQuery(pattern=r'sell_something_(\d+)'))
async def sell_something_handler(event):
    user_id = int(event.pattern_match.group(1))
    await event.answer("Напиши продать (что-то твоё)", alert=False)

@bot.on(events.NewMessage(pattern=r'^(балик|Балик)$'))
async def balance_check(event):
    user_id = event.sender_id
    
    # Добавляем пользователя если его нет
    if not db.user_exists(user_id):
        user = await event.get_sender()
        db.add_user(user_id, user.username, 0)
    
    balance = db.get_premium_points(user_id)
    
    if balance == 0:
        db.add_premium_points(user_id, 1000)
        balance = 1000
    
    await event.respond(f"Ваш баланс: {balance} коинов.")

@bot.on(events.NewMessage(pattern=r'^/магазин'))
async def shop_handler(event):
    user_id = event.sender_id
    
    # Добавляем пользователя если его нет
    if not db.user_exists(user_id):
        user = await event.get_sender()
        db.add_user(user_id, user.username, 0)
    
    balance = db.get_premium_points(user_id)
    
    buttons = [
        [Button.inline("Прем 1д (10 коинов)", data="buy_premium_1d")],
        [Button.inline("Прем 1н (50 коинов)", data="buy_premium_7d")],
        [Button.inline("Прем 1м (125 коинов)", data="buy_premium_30d")],
        [Button.inline("Отдых 1д (100 коинов)", data="buy_rest_1d")],
        [Button.inline(f"Сумма: {balance} очков")]
    ]
    
    await event.respond("Добро пожаловать в магазин!", buttons=buttons)

@bot.on(events.CallbackQuery(pattern='buy_.*'))
async def purchase_handler(event):
    user_id = event.sender_id
    action = event.data.decode('utf-8')
    
    if action == "buy_premium_1d":
        cost = 10; duration = 1; message = "Вы успешно приобрели премиум, премиум статус был добавлен."
    elif action == "buy_premium_7d":
        cost = 50; duration = 7; message = "Вы успешно приобрели премиум, премиум статус был добавлен."
    elif action == "buy_premium_30d":
        cost = 125; duration = 30; message = "Вы успешно приобрели премиум, премиум статус был добавлен."
    elif action == "buy_rest_1d":
        cost = 100; duration = 0; message = "Вы успешно купили отдых, вы освобождены от обязательств стажёра на 1 день!"
    else:
        await event.answer("Неизвестная команда.", alert=True)
        return
    
    if db.get_premium_points(user_id) >= cost:
        db.add_premium_points(user_id, -cost)
        if duration > 0:
            expiry_date = (datetime.now() + timedelta(days=duration)).strftime("%Y-%m-%d %H:%M:%S")
            db.add_premium(user_id, expiry_date)
        await event.answer(message, alert=True)
    else:
        await event.answer("У вас недостаточно коинов!", alert=True)

@bot.on(events.NewMessage)
async def message_handler(event):
    user_id = event.sender_id
    if event.sender.bot: return
    current_time = datetime.now()
    user_message_count[user_id].append(current_time)
    user_message_count[user_id] = [timestamp for timestamp in user_message_count[user_id] if current_time - timestamp < timedelta(seconds=30)]
    
    if len(user_message_count[user_id]) > 8:
        await bot.edit_permissions(event.chat_id, user_id, until_date=current_time + timedelta(minutes=10), send_messages=False, send_media=False, send_stickers=False, send_gifs=False, send_games=False, send_inline=False)
        await event.respond(f"🔇 Пользователь {event.sender.first_name} был замучен за спам на 10 минут!")
        del user_message_count[user_id]

@bot.on(events.NewMessage(pattern='/help'))
async def help_cmd(event):
    help_text = """🤖 **Команды бота:**\n\n📋 **Проверка пользователей:**\n• `Чек [юзернейм/ID]` - проверить пользователя\n• `Чек` (ответом на сообщение) - проверить пользователя\n• `Чек ми/я/себя` - проверить себя\n\n👮‍♂️ **Выдача ролей:**\n• `+стажер` (ответом) - выдать роль стажера\n• `+админ` (ответом) - выдать роль админа\n• `+директор` (ответом) - выдать роль директора\n• `+президент` (ответом) - выдать роль президента\n• `+создатель` (ответом) - выдать роль создателя\n• `+кодер` (ответом) - выдать роль кодера\n• `+гарант` (ответом) - выдать роль гаранта\n\n🔄 **Снятие ролей:**\n• `-стажер` (ответом) - снять роль стажера\n• `-админ` (ответом) - снять роль админа\n• `-директор` (ответом) - снять роль директора\n• `-президент` (ответом) - снять роль президента\n• `-создатель` (ответом) - снять роль создателя\n• `-кодер` (ответом) - снять роль кодера\n• `-гарант` (ответом) - снять роль гаранта\n\n⚠️ **Примечание:**\nКоманды выдачи и снятия ролей доступны только создателю и кодеру!"""
    await event.respond(help_text, parse_mode='md')

@bot.on(events.NewMessage(pattern='/on$'))
async def enable_chat(event):
    user_id = event.sender_id
    if db.get_user_role(user_id) != 10:
        await event.respond("❌ У вас нет прав для выполнения этой команды.")
        return
    
    await bot.edit_permissions(event.chat_id, send_messages=True)
    await event.respond("🔓 Предложка открыта, вы снова можете писать сообщения в чат![⠀](https://i.ibb.co/JFq2r3Dg/image.jpg)")

@bot.on(events.NewMessage(pattern='/off$'))
async def disable_chat(event):
    user_id = event.sender_id
    if db.get_user_role(user_id) != 10:
        await event.respond("❌ У вас нет прав для выполнения этой команды.")
        return
    
    await bot.edit_permissions(event.chat_id, send_messages=False)
    await event.respond("🔒 Предложка закрыта на время, скоро мы вернёмся в строй, следите за новостями![⠀](https://i.ibb.co/JFq2r3Dg/image.jpg)")

@bot.on(events.NewMessage(pattern='/оффтоп'))
async def handle_offtopic_command(event):
    allowed_roles = [1, 6, 7, 8, 9, 10]
    if event.sender_id not in OWNER_ID and db.get_user_role(event.sender_id) not in allowed_roles:
        await event.respond("❌ У вас нет прав для использования этой команды.")
        return
    
    if event.is_reply:
        replied = await event.get_reply_message()
        target_user = await event.client.get_entity(replied.sender_id)
        try:
            await bot.edit_permissions(event.chat_id, target_user.id, until_date=time.time() + 1800, send_messages=False)
            mute_message = f"{target_user.first_name} выдан мут на 30 минут\n\nПричина: Оффтоп\n\nобщайтесь в нашем чате для оффтопа☕"
            keyboard = [[Button.url("Перейти", "https://t.me/+qVD_2vYoWKNmOWJl")]]
            await event.respond(mute_message, buttons=keyboard)
            await replied.delete()
        except Exception as e:
            await event.respond(f"❌ Не могу выдать мут: {e}")
    else:
        await event.respond("❌ Ответьте на сообщение пользователя, которому нужно выдать мут.")

@bot.on(events.NewMessage(pattern='/del'))
async def delete_message(event):
    if event.is_reply:
        replied_message = await event.get_reply_message()
        await replied_message.delete()
    else:
        await event.reply("❌ Пожалуйста, ответьте на сообщение, которое хотите удалить.")

@bot.on(events.NewMessage(pattern='/профиль'))
async def profile_command(event):
    user = await event.get_sender()
    user_id = user.id
    
    # Если пользователя нет в базе - добавляем
    if not db.user_exists(user_id):
        db.add_user(user_id, user.username, 0)
    
    role = db.get_user_role(user_id)
    user_data = db.get_user(user_id)
    
    # Получаем данные как в функции check_soon_handler
    db.add_check(user_id, user_id)
    current_time = datetime.now()
    role_info = ROLES[role]
    user_data = db.get_user(user_id)
    country = user_data[5] if user_data and user_data[5] else "Не указана"
    channel = user_data[6] if user_data and user_data[6] else None
    custom_photo = user_data[8] if user_data else None
    
    # Формируем текст как в check_soon_handler
    response = f"👤 | Пользователь: [{user.first_name}](tg://user/{user.id})\n\n🔍 | ID: `{user.id}`\n\n🤗 | Роль в базе: {role_info['name']}\n\n🌍 | Страна: {country}\n\n📢 | Канал: {channel}\n\n⚖ | Шанс скама: {role_info['scam_chance']}%\n\n📅 {current_time.strftime('%d.%m.%Y')} | 🔍 {db.get_check_count(user_id)}\n\n[Просмотреть медиа]({custom_photo if custom_photo else role_info['preview_url']})"
    
    buttons = [
        [Button.url("👤 Профиль", f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}"), Button.url("🔗 Ссылка", f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}")],
        [Button.url("⚠️ Слить скаммера", "https://t.me/infinityantiscam"), Button.url("⚖️ Аппеляция", "https://t.me/infinityAPPEALS")]
    ]
    
    await event.respond(response, buttons=buttons, parse_mode='md')

def main():
    print("Bot started...")
    bot.run_until_disconnected()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Бот запущен и готов к работе.")
    bot.run_until_disconnected()
