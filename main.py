import asyncio
import json
import sqlite3
import logging
import os
import sys
import signal
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum

from telethon import TelegramClient, events, Button
from telethon.tl.types import Channel, ChatInviteAlready, ChatInvite
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import ChannelParticipant
from telethon.errors import UserNotParticipantError, ChannelInvalidError

# Получаем переменные окружения или используем значения по умолчанию
API_ID = int(os.getenv('API_ID', 27231812))
API_HASH = os.getenv('API_HASH', '59d6d299a99f9bb97fcbf5645d9d91e9')
BOT_TOKEN = os.getenv('BOT_TOKEN', '8241926742:AAFsM9GYYpl8e-q1PVVVV6SoFQYgmRIZAsY')
ADMIN_ID = int(os.getenv('ADMIN_ID', 262511724))

# Инициализация клиента
client = TelegramClient('stars_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        self.conn = sqlite3.connect('stars_bot.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.init_db()

    def init_db(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                stars INTEGER DEFAULT 0,
                referrals INTEGER DEFAULT 0,
                referral_id TEXT UNIQUE,
                referrer_id INTEGER,
                verified BOOLEAN DEFAULT FALSE,
                total_withdrawn INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS sponsors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                link TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                active BOOLEAN DEFAULT TRUE
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                reward INTEGER NOT NULL,
                active BOOLEAN DEFAULT TRUE
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS completed_tasks (
                user_id INTEGER,
                task_id INTEGER,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, task_id)
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS promocodes (
                code TEXT PRIMARY KEY,
                reward INTEGER NOT NULL,
                usage_limit INTEGER DEFAULT 1,
                times_used INTEGER DEFAULT 0,
                active BOOLEAN DEFAULT TRUE
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS used_promocodes (
                user_id INTEGER,
                code TEXT,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, code)
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')

        default_settings = [
            ('min_withdrawal', '100'),
            ('referral_reward', '3'),
            ('top_rewards', '[40, 30, 20, 10, 10]'),
            ('channel_requests', '-1001234567890')
        ]

        for key, value in default_settings:
            self.cursor.execute(
                'INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
                (key, value)
            )

        self.conn.commit()

    def register_user(self, user_id: int, username: str, first_name: str, last_name: str, referrer_id: int = None):
        referral_id = f"ref_{user_id}"
        self.cursor.execute('''
            INSERT OR IGNORE INTO users 
            (user_id, username, first_name, last_name, referral_id, referrer_id) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name, referral_id, referrer_id))

        if referrer_id:
            self.cursor.execute('''
                UPDATE users SET referrals = referrals + 1 
                WHERE user_id = ?
            ''', (referrer_id,))
            reward = int(self.get_setting('referral_reward'))
            self.add_stars(referrer_id, reward)

        self.conn.commit()

    def get_user(self, user_id: int) -> dict:
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = self.cursor.fetchone()
        if row:
            return {
                'user_id': row[0],
                'username': row[1],
                'first_name': row[2],
                'last_name': row[3],
                'stars': row[4],
                'referrals': row[5],
                'referral_id': row[6],
                'referrer_id': row[7],
                'verified': bool(row[8]),
                'total_withdrawn': row[9],
                'created_at': row[10]
            }
        return None

    def update_verification(self, user_id: int, verified: bool):
        self.cursor.execute(
            'UPDATE users SET verified = ? WHERE user_id = ?',
            (verified, user_id)
        )
        self.conn.commit()

    def add_stars(self, user_id: int, amount: int):
        self.cursor.execute(
            'UPDATE users SET stars = stars + ? WHERE user_id = ?',
            (amount, user_id)
        )
        self.conn.commit()

    def deduct_stars(self, user_id: int, amount: int):
        self.cursor.execute(
            'UPDATE users SET stars = stars - ? WHERE user_id = ?',
            (amount, user_id)
        )
        self.conn.commit()

    def get_top_referrals(self, limit: int = 10) -> List[dict]:
        self.cursor.execute('''
            SELECT user_id, username, first_name, referrals, stars 
            FROM users 
            ORDER BY referrals DESC 
            LIMIT ?
        ''', (limit,))
        return [
            {
                'user_id': row[0],
                'username': row[1],
                'first_name': row[2],
                'referrals': row[3],
                'stars': row[4]
            }
            for row in self.cursor.fetchall()
        ]

    def get_top_withdrawals(self, limit: int = 10) -> List[dict]:
        self.cursor.execute('''
            SELECT user_id, username, first_name, total_withdrawn 
            FROM users 
            ORDER BY total_withdrawn DESC 
            LIMIT ?
        ''', (limit,))
        return [
            {
                'user_id': row[0],
                'username': row[1],
                'first_name': row[2],
                'total_withdrawn': row[3]
            }
            for row in self.cursor.fetchall()
        ]

    def add_sponsor(self, name: str, link: str, channel_id: str):
        self.cursor.execute('''
            INSERT INTO sponsors (name, link, channel_id) 
            VALUES (?, ?, ?)
        ''', (name, link, channel_id))
        self.conn.commit()

    def get_sponsors(self, active_only: bool = True) -> List[dict]:
        query = 'SELECT * FROM sponsors'
        if active_only:
            query += ' WHERE active = TRUE'
        self.cursor.execute(query)
        return [
            {
                'id': row[0],
                'name': row[1],
                'link': row[2],
                'channel_id': row[3],
                'active': bool(row[4])
            }
            for row in self.cursor.fetchall()
        ]

    def get_sponsor(self, sponsor_id: int) -> dict:
        self.cursor.execute('SELECT * FROM sponsors WHERE id = ?', (sponsor_id,))
        row = self.cursor.fetchone()
        if row:
            return {
                'id': row[0],
                'name': row[1],
                'link': row[2],
                'channel_id': row[3],
                'active': bool(row[4])
            }
        return None

    def update_sponsor_status(self, sponsor_id: int, active: bool):
        self.cursor.execute(
            'UPDATE sponsors SET active = ? WHERE id = ?',
            (active, sponsor_id)
        )
        self.conn.commit()

    def delete_sponsor(self, sponsor_id: int):
        self.cursor.execute('DELETE FROM sponsors WHERE id = ?', (sponsor_id,))
        self.conn.commit()

    def add_task(self, description: str, reward: int):
        self.cursor.execute('''
            INSERT INTO tasks (description, reward) 
            VALUES (?, ?)
        ''', (description, reward))
        self.conn.commit()

    def get_tasks(self, user_id: int = None) -> List[dict]:
        self.cursor.execute('SELECT * FROM tasks WHERE active = TRUE')
        tasks = []
        for row in self.cursor.fetchall():
            task = {
                'id': row[0],
                'description': row[1],
                'reward': row[2],
                'active': bool(row[3])
            }
            if user_id:
                self.cursor.execute(
                    'SELECT 1 FROM completed_tasks WHERE user_id = ? AND task_id = ?',
                    (user_id, task['id'])
                )
                task['completed'] = self.cursor.fetchone() is not None
            tasks.append(task)
        return tasks

    def get_all_tasks(self) -> List[dict]:
        self.cursor.execute('SELECT * FROM tasks')
        return [
            {
                'id': row[0],
                'description': row[1],
                'reward': row[2],
                'active': bool(row[3])
            }
            for row in self.cursor.fetchall()
        ]

    def get_task(self, task_id: int) -> dict:
        self.cursor.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
        row = self.cursor.fetchone()
        if row:
            return {
                'id': row[0],
                'description': row[1],
                'reward': row[2],
                'active': bool(row[3])
            }
        return None

    def complete_task(self, user_id: int, task_id: int):
        self.cursor.execute('''
            INSERT OR IGNORE INTO completed_tasks (user_id, task_id) 
            VALUES (?, ?)
        ''', (user_id, task_id))
        self.cursor.execute('SELECT reward FROM tasks WHERE id = ?', (task_id,))
        reward = self.cursor.fetchone()[0]
        self.add_stars(user_id, reward)
        self.conn.commit()
        return reward

    def update_task_status(self, task_id: int, active: bool):
        self.cursor.execute(
            'UPDATE tasks SET active = ? WHERE id = ?',
            (active, task_id)
        )
        self.conn.commit()

    def delete_task(self, task_id: int):
        self.cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        self.conn.commit()

    def add_promocode(self, code: str, reward: int, usage_limit: int = 1):
        self.cursor.execute('''
            INSERT INTO promocodes (code, reward, usage_limit) 
            VALUES (?, ?, ?)
        ''', (code, reward, usage_limit))
        self.conn.commit()

    def get_promocode(self, code: str) -> dict:
        self.cursor.execute('SELECT * FROM promocodes WHERE code = ?', (code,))
        row = self.cursor.fetchone()
        if row:
            return {
                'code': row[0],
                'reward': row[1],
                'usage_limit': row[2],
                'times_used': row[3],
                'active': bool(row[4])
            }
        return None

    def get_all_promocodes(self) -> List[dict]:
        self.cursor.execute('SELECT * FROM promocodes')
        return [
            {
                'code': row[0],
                'reward': row[1],
                'usage_limit': row[2],
                'times_used': row[3],
                'active': bool(row[4])
            }
            for row in self.cursor.fetchall()
        ]

    def use_promocode(self, user_id: int, code: str) -> bool:
        promocode = self.get_promocode(code)
        if not promocode or not promocode['active']:
            return False
        if promocode['times_used'] >= promocode['usage_limit']:
            return False
        self.cursor.execute(
            'SELECT 1 FROM used_promocodes WHERE user_id = ? AND code = ?',
            (user_id, code)
        )
        if self.cursor.fetchone():
            return False
        self.cursor.execute('''
            INSERT INTO used_promocodes (user_id, code) 
            VALUES (?, ?)
        ''', (user_id, code))
        self.cursor.execute(
            'UPDATE promocodes SET times_used = times_used + 1 WHERE code = ?',
            (code,)
        )
        self.add_stars(user_id, promocode['reward'])
        self.conn.commit()
        return True

    def update_promocode_status(self, code: str, active: bool):
        self.cursor.execute(
            'UPDATE promocodes SET active = ? WHERE code = ?',
            (active, code)
        )
        self.conn.commit()

    def delete_promocode(self, code: str):
        self.cursor.execute('DELETE FROM promocodes WHERE code = ?', (code,))
        self.conn.commit()

    def create_withdrawal(self, user_id: int, amount: int) -> int:
        self.cursor.execute('''
            INSERT INTO withdrawals (user_id, amount) 
            VALUES (?, ?)
        ''', (user_id, amount))
        withdrawal_id = self.cursor.lastrowid
        self.deduct_stars(user_id, amount)
        self.conn.commit()
        return withdrawal_id

    def get_withdrawals(self, status: str = None) -> List[dict]:
        query = 'SELECT * FROM withdrawals'
        if status:
            query += f" WHERE status = '{status}'"
        query += ' ORDER BY created_at DESC'
        self.cursor.execute(query)
        return [
            {
                'id': row[0],
                'user_id': row[1],
                'amount': row[2],
                'status': row[3],
                'created_at': row[4]
            }
            for row in self.cursor.fetchall()
        ]

    def update_withdrawal_status(self, withdrawal_id: int, status: str):
        self.cursor.execute(
            'UPDATE withdrawals SET status = ? WHERE id = ?',
            (status, withdrawal_id)
        )
        if status == 'completed':
            self.cursor.execute(
                'SELECT user_id, amount FROM withdrawals WHERE id = ?',
                (withdrawal_id,)
            )
            result = self.cursor.fetchone()
            if result:
                user_id, amount = result
                self.cursor.execute('''
                    UPDATE users SET total_withdrawn = total_withdrawn + ? 
                    WHERE user_id = ?
                ''', (amount, user_id))
        self.conn.commit()

    def get_setting(self, key: str, default: str = None) -> str:
        self.cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        row = self.cursor.fetchone()
        return row[0] if row else default

    def update_setting(self, key: str, value: str):
        self.cursor.execute('''
            INSERT OR REPLACE INTO settings (key, value) 
            VALUES (?, ?)
        ''', (key, str(value)))
        self.conn.commit()

    def get_statistics(self) -> dict:
        stats = {}
        self.cursor.execute('SELECT COUNT(*) FROM users')
        stats['total_users'] = self.cursor.fetchone()[0]
        self.cursor.execute('SELECT COUNT(*) FROM users WHERE verified = TRUE')
        stats['verified_users'] = self.cursor.fetchone()[0]
        self.cursor.execute('SELECT SUM(stars) FROM users')
        stats['total_stars'] = self.cursor.fetchone()[0] or 0
        self.cursor.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'pending'")
        stats['pending_withdrawals'] = self.cursor.fetchone()[0]
        self.cursor.execute('SELECT COUNT(*) FROM sponsors WHERE active = TRUE')
        stats['active_sponsors'] = self.cursor.fetchone()[0]
        self.cursor.execute('SELECT COUNT(*) FROM tasks WHERE active = TRUE')
        stats['active_tasks'] = self.cursor.fetchone()[0]
        self.cursor.execute('SELECT COUNT(*) FROM promocodes WHERE active = TRUE')
        stats['active_promocodes'] = self.cursor.fetchone()[0]
        return stats


db = Database()


class Keyboards:
    @staticmethod
    def main_menu(user_verified: bool = False, user_id: int = None):
        if not user_verified:
            return [
                [Button.inline("✅ Проверить подписки", b"check_subscriptions")],
                [Button.inline("📊 Профиль", b"profile")]
            ]

        buttons = [
            [Button.inline("💰 Заработать", b"earn_stars"), Button.inline("📊 Профиль", b"profile")],
            [Button.inline("🏆 Топы", b"tops"), Button.inline("🎁 Промокод", b"promocode")],
            [Button.inline("💸 Вывод", b"withdraw")]
        ]

        if user_id == ADMIN_ID:
            buttons.append([Button.inline("⚙️ Админ-панель", b"admin_panel")])

        return buttons

    @staticmethod
    def sponsors_menu(sponsors: List[dict]):
        buttons = []
        for sponsor in sponsors:
            buttons.append([Button.url(sponsor['name'], sponsor['link'])])

        buttons.append([Button.inline("✅ Проверить подписки", b"check_subscriptions")])
        buttons.append([Button.inline("◀️ Назад", b"back_to_main")])
        return buttons

    @staticmethod
    def tasks_menu(tasks: List[dict]):
        buttons = []
        for task in tasks:
            status = "✅" if task.get('completed') else "🔘"
            button_text = f"{status} +{task['reward']}⭐"
            buttons.append([Button.inline(button_text, f"task_{task['id']}".encode())])
        buttons.append([Button.inline("◀️ Назад", b"back_to_main")])
        return buttons

    @staticmethod
    def admin_menu():
        return [
            [Button.inline("📢 Спонсоры", b"admin_sponsors"), Button.inline("📋 Задания", b"admin_tasks")],
            [Button.inline("🎁 Промокоды", b"admin_promocodes"), Button.inline("⚙️ Настройки", b"admin_settings")],
            [Button.inline("📊 Статистика", b"admin_stats"), Button.inline("💸 Выводы", b"admin_withdrawals")],
            [Button.inline("◀️ Главное меню", b"back_to_main")]
        ]

    @staticmethod
    def sponsors_admin_menu(sponsors: List[dict]):
        buttons = []
        for sponsor in sponsors:
            status = "✅" if sponsor['active'] else "❌"
            button_text = f"{status} {sponsor['name'][:20]}"
            buttons.append([
                Button.inline(button_text, f"sponsor_{sponsor['id']}".encode()),
                Button.inline("🗑️", f"delete_sponsor_{sponsor['id']}".encode())
            ])
        buttons.append([Button.inline("➕ Добавить спонсора", b"add_sponsor")])
        buttons.append([Button.inline("◀️ Назад", b"admin_panel")])
        return buttons

    @staticmethod
    def tasks_admin_menu(tasks: List[dict]):
        buttons = []
        for task in tasks:
            status = "✅" if task['active'] else "❌"
            button_text = f"{status} #{task['id']}"
            buttons.append([
                Button.inline(button_text, f"task_admin_{task['id']}".encode()),
                Button.inline("🗑️", f"delete_task_{task['id']}".encode())
            ])
        buttons.append([Button.inline("➕ Добавить задание", b"add_task")])
        buttons.append([Button.inline("◀️ Назад", b"admin_panel")])
        return buttons

    @staticmethod
    def promocodes_admin_menu(promocodes: List[dict]):
        buttons = []
        for promo in promocodes:
            status = "✅" if promo['active'] else "❌"
            button_text = f"{status} {promo['code']}"
            buttons.append([
                Button.inline(button_text, f"promo_admin_{promo['code']}".encode()),
                Button.inline("🗑️", f"delete_promo_{promo['code']}".encode())
            ])
        buttons.append([Button.inline("➕ Добавить промокод", b"add_promocode")])
        buttons.append([Button.inline("◀️ Назад", b"admin_panel")])
        return buttons

    @staticmethod
    def settings_menu():
        min_withdrawal = db.get_setting('min_withdrawal')
        referral_reward = db.get_setting('referral_reward')
        return [
            [Button.inline(f"💰 Мин. вывод: {min_withdrawal}⭐", b"setting_min_withdrawal")],
            [Button.inline(f"👥 Реферал: {referral_reward}⭐", b"setting_referral_reward")],
            [Button.inline("◀️ Назад", b"admin_panel")]
        ]

    @staticmethod
    def tops_menu():
        return [
            [Button.inline("🏆 Топ рефералов", b"top_referrals"), Button.inline("💰 Топ выводов", b"top_withdrawals")],
            [Button.inline("◀️ Назад", b"back_to_main")]
        ]

    @staticmethod
    def confirm_withdrawal():
        return [
            [Button.inline("✅ Подтвердить", b"confirm_withdraw"), Button.inline("❌ Отмена", b"cancel_withdraw")]
        ]

    @staticmethod
    def sponsor_detail_menu(sponsor_id: int, is_active: bool):
        if is_active:
            return [
                [Button.inline("❌ Деактивировать", f"toggle_sponsor_{sponsor_id}".encode())],
                [Button.inline("◀️ Назад", b"admin_sponsors")]
            ]
        else:
            return [
                [Button.inline("✅ Активировать", f"toggle_sponsor_{sponsor_id}".encode())],
                [Button.inline("◀️ Назад", b"admin_sponsors")]
            ]

    @staticmethod
    def task_detail_menu(task_id: int, is_active: bool):
        if is_active:
            return [
                [Button.inline("❌ Деактивировать", f"toggle_task_{task_id}".encode())],
                [Button.inline("◀️ Назад", b"admin_tasks")]
            ]
        else:
            return [
                [Button.inline("✅ Активировать", f"toggle_task_{task_id}".encode())],
                [Button.inline("◀️ Назад", b"admin_tasks")]
            ]

    @staticmethod
    def promocode_detail_menu(code: str, is_active: bool):
        if is_active:
            return [
                [Button.inline("❌ Деактивировать", f"toggle_promo_{code}".encode())],
                [Button.inline("◀️ Назад", b"admin_promocodes")]
            ]
        else:
            return [
                [Button.inline("✅ Активировать", f"toggle_promo_{code}".encode())],
                [Button.inline("◀️ Назад", b"admin_promocodes")]
            ]

    @staticmethod
    def withdrawals_admin_menu():
        return [
            [Button.inline("⏳ Ожидающие", b"pending_withdrawals")],
            [Button.inline("✅ Завершенные", b"completed_withdrawals")],
            [Button.inline("❌ Отклоненные", b"rejected_withdrawals")],
            [Button.inline("◀️ Назад", b"admin_panel")]
        ]


class AdminState:
    ADD_SPONSOR_NAME = "add_sponsor_name"
    ADD_SPONSOR_LINK = "add_sponsor_link"
    ADD_SPONSOR_CHANNEL = "add_sponsor_channel"
    ADD_TASK_DESC = "add_task_desc"
    ADD_TASK_REWARD = "add_task_reward"
    ADD_PROMOCODE = "add_promocode"
    ADD_PROMOCODE_REWARD = "add_promocode_reward"
    ADD_PROMOCODE_LIMIT = "add_promocode_limit"
    SETTING_MIN_WITHDRAWAL = "setting_min_withdrawal"
    SETTING_REFERRAL_REWARD = "setting_referral_reward"


admin_states = {}


async def check_user_subscriptions(user_id: int) -> bool:
    sponsors = db.get_sponsors(active_only=True)
    if not sponsors:
        return True

    for sponsor in sponsors:
        channel_id = sponsor['channel_id']
        try:
            if channel_id.startswith('@'):
                channel_entity = await client.get_entity(channel_id)
            elif channel_id.startswith('-100'):
                channel_entity = await client.get_entity(int(channel_id))
            else:
                channel_entity = await client.get_entity(int(channel_id))
        except:
            try:
                channel_entity = await client.get_entity(channel_id)
            except:
                return False

        try:
            await client(GetParticipantRequest(
                channel=channel_entity,
                participant=user_id
            ))
        except UserNotParticipantError:
            return False
        except:
            return False

    return True


async def verify_user(user_id: int) -> bool:
    is_subscribed = await check_user_subscriptions(user_id)
    db.update_verification(user_id, is_subscribed)
    return is_subscribed


async def check_and_update_verification(user_id: int) -> bool:
    return await verify_user(user_id)


async def require_verification(event):
    user_id = event.sender_id
    user_data = db.get_user(user_id)

    if not user_data:
        user = await event.get_sender()
        db.register_user(
            user_id=user_id,
            username=user.username or '',
            first_name=user.first_name or '',
            last_name=user.last_name or ''
        )
        user_data = db.get_user(user_id)

    is_verified = await check_and_update_verification(user_id)

    if not is_verified:
        sponsors = db.get_sponsors(active_only=True)
        if sponsors:
            sponsors_text = "📋 **СПОНСОРЫ**\n\n"
            for sponsor in sponsors:
                sponsors_text += f"• {sponsor['name']}\n"

            await event.respond(
                f"⚠️ **Чтобы получать бесплатно робуксы/звезды/голду необходимо подписаться на всех спонсоров!**\n\n"
                f"{sponsors_text}\n"
                f"После подписки нажмите кнопку **'✅ Проверить подписки'**",
                buttons=Keyboards.sponsors_menu(sponsors)
            )
        return False

    return True


@client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user = await event.get_sender()
    user_id = user.id

    args = event.message.message.split()
    referrer_id = None
    if len(args) > 1:
        try:
            ref_arg = args[1]
            if ref_arg.startswith('ref_'):
                referrer_id = int(ref_arg.split('_')[1])
        except:
            pass

    db.register_user(
        user_id=user_id,
        username=user.username or '',
        first_name=user.first_name or '',
        last_name=user.last_name or '',
        referrer_id=referrer_id
    )

    user_data = db.get_user(user_id)
    is_verified = await check_and_update_verification(user_id)

    if not is_verified:
        sponsors = db.get_sponsors(active_only=True)
        if sponsors:
            sponsors_text = "📋 **СПОНСОРЫ**\n\n"
            for sponsor in sponsors:
                sponsors_text += f"• {sponsor['name']}\n"

            message = f"""
🎯 **Добро пожаловать в бота для заработка Telegram Stars!**

{sponsors_text}
⚠️ **Для доступа к функциям бота необходимо подписаться на всех спонсоров!**

После подписки нажмите кнопку **"✅ Проверить подписки"**
            """
            await event.respond(message, buttons=Keyboards.sponsors_menu(sponsors))
        else:
            db.update_verification(user_id, True)
            message = f"""
✅ **Регистрация завершена!**

👤 Добро пожаловать, {user.first_name}!
💰 Ваш баланс: **0⭐**
👥 Рефералов: **0**

Выберите действие:
            """
            await event.respond(message, buttons=Keyboards.main_menu(user_verified=True, user_id=user_id))
    else:
        message = f"""
👋 С возвращением, {user.first_name}!

💰 Баланс: **{user_data['stars']}⭐**
👥 Рефералов: **{user_data['referrals']}**

Выберите действие:
        """
        await event.respond(message, buttons=Keyboards.main_menu(user_verified=True, user_id=user_id))

    if referrer_id:
        try:
            referrer_data = db.get_user(referrer_id)
            if referrer_data:
                await client.send_message(
                    referrer_id,
                    f"🎉 По вашей реферальной ссылке зарегистрировался новый пользователь: @{user.username or user.first_name}\n"
                    f"💰 Вам начислено +{db.get_setting('referral_reward')}⭐ за реферала!"
                )
        except:
            pass


@client.on(events.CallbackQuery(pattern=b'check_subscriptions'))
async def check_subscriptions_handler(event):
    user_id = event.sender_id
    try:
        await event.delete()
    except:
        pass

    is_verified = await check_and_update_verification(user_id)

    if is_verified:
        user_data = db.get_user(user_id)
        temp_message = await event.respond("✅ **Отлично!** Вы подписаны на все спонсорские каналы!")
        await asyncio.sleep(2)
        await temp_message.delete()

        user = await event.get_sender()
        message = f"""
✅ **Регистрация завершена!**

👤 Добро пожаложествен, {user.first_name}!
💰 Ваш баланс: **{user_data['stars']}⭐**
👥 Рефералов: **{user_data['referrals']}**

Выберите действие:
        """
        await event.respond(message, buttons=Keyboards.main_menu(user_verified=True, user_id=user_id))
    else:
        sponsors = db.get_sponsors(active_only=True)
        await event.respond(
            "❌ **Вы не подписаны на все спонсорские каналы!**\n"
            "Пожалуйста, подпишитесь на всех спонсоров и попробуйте снова.",
            buttons=Keyboards.sponsors_menu(sponsors)
        )


@client.on(events.CallbackQuery(pattern=b'back_to_main'))
async def back_to_main_handler(event):
    user_id = event.sender_id
    if not await require_verification(event):
        return

    user_data = db.get_user(user_id)
    try:
        await event.delete()
    except:
        pass

    message = f"""
👤 **Ваш профиль**
💰 Баланс: **{user_data['stars']}⭐**
👥 Рефералов: **{user_data['referrals']}**
📊 Всего выведено: **{user_data['total_withdrawn']}⭐**

Выберите действие:
    """
    await event.respond(message, buttons=Keyboards.main_menu(user_verified=user_data['verified'], user_id=user_id))


@client.on(events.CallbackQuery(pattern=b'profile'))
async def profile_handler(event):
    if not await require_verification(event):
        return

    user_id = event.sender_id
    user_data = db.get_user(user_id)
    me = await client.get_me()
    referral_link = f"https://t.me/{me.username}?start=ref_{user_id}"

    try:
        await event.delete()
    except:
        pass

    message = f"""
👤 **ПРОФИЛЬ**

📝 **Имя:** {user_data['first_name']} {user_data['last_name']}
🔗 **Username:** @{user_data['username'] or 'Нет'}

💰 **Баланс:** {user_data['stars']}⭐
👥 **Рефералов:** {user_data['referrals']}
📊 **Всего выведено:** {user_data['total_withdrawn']}⭐

🔗 **Ваша реферальная ссылка:**
`{referral_link}`

💎 **Приглашайте друзей и получайте {db.get_setting('referral_reward')}⭐ за каждого!**
    """
    await event.respond(message, buttons=Keyboards.main_menu(user_verified=user_data['verified'], user_id=user_id))


@client.on(events.CallbackQuery(pattern=b'earn_stars'))
async def earn_stars_handler(event):
    if not await require_verification(event):
        return

    user_id = event.sender_id
    user_data = db.get_user(user_id)
    try:
        await event.delete()
    except:
        pass

    tasks = db.get_tasks(user_id)
    if not tasks:
        await event.respond(
            "📭 На данный момент нет доступных заданий.\nЗагляните позже!",
            buttons=Keyboards.main_menu(user_verified=True, user_id=user_id)
        )
        return

    message = "📋 **ДОСТУПНЫЕ ЗАДАНИЯ**\n\n"
    for task in tasks:
        status = "✅ Выполнено" if task.get('completed') else "🟢 Доступно"
        message += f"• {task['description']}\n"
        message += f"  Награда: **+{task['reward']}⭐**\n"
        message += f"  Статус: {status}\n\n"

    await event.respond(message, buttons=Keyboards.tasks_menu(tasks))


@client.on(events.CallbackQuery(pattern=b'task_'))
async def task_handler(event):
    if not await require_verification(event):
        return

    user_id = event.sender_id
    task_id = int(event.data.decode().split('_')[1])
    user_data = db.get_user(user_id)

    tasks = db.get_tasks(user_id)
    task = next((t for t in tasks if t['id'] == task_id), None)

    if not task:
        await event.respond("❌ Задание не найдено!")
        return

    if task.get('completed'):
        await event.respond("ℹ️ Вы уже выполнили это задание!")
        return

    reward = db.complete_task(user_id, task_id)
    try:
        await event.delete()
    except:
        pass

    await event.respond(
        f"✅ **Задание выполнено!**\n"
        f"🎉 Вам начислено **+{reward}⭐**\n\n"
        f"💰 Ваш баланс: **{user_data['stars'] + reward}⭐**"
    )
    await earn_stars_handler(event)


@client.on(events.CallbackQuery(pattern=b'tops'))
async def tops_handler(event):
    if not await require_verification(event):
        return
    try:
        await event.delete()
    except:
        pass
    await event.respond("🏆 **ТОПЫ**\n\nВыберите тип топа для просмотра:", buttons=Keyboards.tops_menu())


@client.on(events.CallbackQuery(pattern=b'top_referrals'))
async def top_referrals_handler(event):
    if not await require_verification(event):
        return
    try:
        await event.delete()
    except:
        pass
    top_users = db.get_top_referrals(10)
    message = "🏆 **ТОП-10 ПО РЕФЕРАЛАМ**\n\n"
    for i, user in enumerate(top_users, 1):
        medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f"{i}."
        username = f"@{user['username']}" if user['username'] else user['first_name']
        message += f"{medal} {username} - {user['referrals']} реф. ({user['stars']}⭐)\n"
    message += f"\n🎁 **На этой неделе топ-5 получают бонусные звёзды!**"
    await event.respond(message, buttons=Keyboards.tops_menu())


@client.on(events.CallbackQuery(pattern=b'top_withdrawals'))
async def top_withdrawals_handler(event):
    if not await require_verification(event):
        return
    try:
        await event.delete()
    except:
        pass
    top_users = db.get_top_withdrawals(10)
    message = "💰 **ТОП-10 ПО ВЫВОДАМ**\n\n"
    for i, user in enumerate(top_users, 1):
        medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f"{i}."
        username = f"@{user['username']}" if user['username'] else user['first_name']
        message += f"{medal} {username} - {user['total_withdrawn']}⭐\n"
    await event.respond(message, buttons=Keyboards.tops_menu())


@client.on(events.CallbackQuery(pattern=b'promocode'))
async def promocode_handler(event):
    if not await require_verification(event):
        return
    try:
        await event.delete()
    except:
        pass
    await event.respond(
        "🎁 **АКТИВАЦИЯ ПРОМОКОДА**\n\n"
        "Введите промокод в формате:\n"
        "`/promo КОД`\n\n"
        "Например: `/promo WELCOME100`",
        buttons=Keyboards.main_menu(user_verified=True, user_id=event.sender_id)
    )


@client.on(events.NewMessage(pattern='/promo'))
async def activate_promocode_handler(event):
    user_id = event.sender_id
    user_data = db.get_user(user_id)

    is_verified = await check_and_update_verification(user_id)
    if not is_verified:
        sponsors = db.get_sponsors(active_only=True)
        if sponsors:
            sponsors_text = "📋 **СПОНСОРЫ**\n\n"
            for sponsor in sponsors:
                sponsors_text += f"• {sponsor['name']}\n"
            await event.respond(
                f"⚠️ **Для доступа к функциям бота необходимо подписаться на всех спонсоров!**\n\n"
                f"{sponsors_text}\n"
                f"После подписки нажмите кнопку **'✅ Проверить подписки'**",
                buttons=Keyboards.sponsors_menu(sponsors)
            )
        return

    args = event.message.message.split()
    if len(args) < 2:
        await event.respond("❌ Неверный формат! Используйте: `/promo КОД`")
        return

    code = args[1].upper()
    success = db.use_promocode(user_id, code)

    if success:
        promocode = db.get_promocode(code)
        await event.respond(
            f"✅ **Промокод активирован!**\n"
            f"🎉 Вам начислено **+{promocode['reward']}⭐**\n\n"
            f"💰 Ваш баланс: **{user_data['stars'] + promocode['reward']}⭐**"
        )
    else:
        await event.respond(
            "❌ **Не удалось активировать промокод!**\n"
            "Возможные причины:\n"
            "• Промокод не существует\n"
            "• Промокод неактивен\n"
            "• Вы уже использовали этот промокод\n"
            "• Лимит использований исчерпан"
        )


@client.on(events.CallbackQuery(pattern=b'withdraw'))
async def withdraw_handler(event):
    if not await require_verification(event):
        return

    user_id = event.sender_id
    user_data = db.get_user(user_id)
    min_withdrawal = int(db.get_setting('min_withdrawal'))

    if user_data['stars'] < min_withdrawal:
        try:
            await event.delete()
        except:
            pass
        await event.respond(
            f"❌ **Недостаточно средств для вывода!**\n\n"
            f"💰 Ваш баланс: **{user_data['stars']}⭐**\n"
            f"📊 Минимальная сумма вывода: **{min_withdrawal}⭐**\n\n"
            f"Выполняйте задания и приглашайте друзей, чтобы заработать больше!",
            buttons=Keyboards.main_menu(user_verified=True, user_id=user_id)
        )
        return

    try:
        await event.delete()
    except:
        pass

    message = f"""
💸 **ВЫВОД СРЕДСТВ**

💰 Ваш баланс: **{user_data['stars']}⭐**
📊 Минимальная сумма вывода: **{min_withdrawal}⭐**

⚠️ **Внимание!** При создании заявки все ваши звёзды будут списаны и зарезервированы для вывода.

Вы хотите вывести **{user_data['stars']}⭐**?
    """
    await event.respond(message, buttons=Keyboards.confirm_withdrawal())


@client.on(events.CallbackQuery(pattern=b'confirm_withdraw'))
async def confirm_withdrawal_handler(event):
    if not await require_verification(event):
        return

    user_id = event.sender_id
    user_data = db.get_user(user_id)
    withdrawal_id = db.create_withdrawal(user_id, user_data['stars'])
    requests_channel = db.get_setting('channel_requests')

    try:
        await event.delete()
    except:
        pass

    message = f"""
✅ **Заявка на вывод создана!**

📊 Номер заявки: **#{withdrawal_id}**
💰 Сумма: **{user_data['stars']}⭐**
⏰ Статус: **Ожидает обработки**

🔔 Администратор уведомлен о вашей заявке.
Ожидайте обработки в течение 24 часов.

💬 Для связи: {requests_channel}
    """
    await event.respond(message, buttons=Keyboards.main_menu(user_verified=True, user_id=user_id))

    if ADMIN_ID:
        admin_message = f"""
🆕 **НОВАЯ ЗАЯВКА НА ВЫВОД**

👤 Пользователь: @{user_data['username'] or user_data['first_name']}
🆔 ID: {user_id}
📊 Номер: #{withdrawal_id}
💰 Сумма: {user_data['stars']}⭐

✅ Для подтверждения: `/approve {withdrawal_id}`
❌ Для отклонения: `/reject {withdrawal_id}`
        """
        try:
            await client.send_message(ADMIN_ID, admin_message)
        except:
            pass


@client.on(events.CallbackQuery(pattern=b'cancel_withdraw'))
async def cancel_withdrawal_handler(event):
    if not await require_verification(event):
        return
    try:
        await event.delete()
    except:
        pass
    await event.respond(
        "❌ Вывод средств отменен.",
        buttons=Keyboards.main_menu(user_verified=True, user_id=event.sender_id)
    )


@client.on(events.CallbackQuery(pattern=b'admin_panel'))
async def admin_panel_handler(event):
    if event.sender_id != ADMIN_ID:
        await event.respond("❌ У вас нет доступа к админ-панели!")
        return
    try:
        await event.delete()
    except:
        pass
    await event.respond("⚙️ **АДМИН-ПАНЕЛЬ**\n\nВыберите раздел для управления:", buttons=Keyboards.admin_menu())


@client.on(events.CallbackQuery(pattern=b'admin_sponsors'))
async def admin_sponsors_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    try:
        await event.delete()
    except:
        pass
    sponsors = db.get_sponsors(active_only=False)
    if not sponsors:
        message = "📭 Список спонсоров пуст.\n\nНажмите '➕ Добавить спонсора' чтобы добавить нового спонсора."
    else:
        message = "📢 **УПРАВЛЕНИЕ СПОНСОРАМИ**\n\n"
        for sponsor in sponsors:
            status = "✅ Активен" if sponsor['active'] else "❌ Неактивен"
            message += f"• {sponsor['name']}\n  Ссылка: {sponsor['link']}\n  ID: {sponsor['channel_id']}\n  Статус: {status}\n\n"
    await event.respond(message, buttons=Keyboards.sponsors_admin_menu(sponsors))


@client.on(events.CallbackQuery(pattern=b'sponsor_'))
async def sponsor_detail_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    try:
        sponsor_id = int(event.data.decode().split('_')[1])
    except:
        return

    sponsor = db.get_sponsor(sponsor_id)
    if not sponsor:
        await event.respond("❌ Спонсор не найден!")
        return

    try:
        await event.delete()
    except:
        pass

    status = "✅ Активен" if sponsor['active'] else "❌ Неактивен"
    message = f"""
📋 **ИНФОРМАЦИЯ О СПОНСОРЕ**

🏷️ **Название:** {sponsor['name']}
🔗 **Ссылка:** {sponsor['link']}
🆔 **ID канала:** {sponsor['channel_id']}
📊 **Статус:** {status}

Выберите действие:
"""
    await event.respond(message, buttons=Keyboards.sponsor_detail_menu(sponsor_id, sponsor['active']))


@client.on(events.CallbackQuery(pattern=b'toggle_sponsor_'))
async def toggle_sponsor_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    try:
        sponsor_id = int(event.data.decode().split('_')[2])
    except:
        return

    sponsor = db.get_sponsor(sponsor_id)
    if not sponsor:
        await event.respond("❌ Спонсор не найден!")
        return

    new_status = not sponsor['active']
    db.update_sponsor_status(sponsor_id, new_status)
    status_text = "активирован" if new_status else "деактивирован"

    try:
        await event.delete()
    except:
        pass

    await event.respond(f"✅ Спонсор '{sponsor['name']}' {status_text}!")
    await admin_sponsors_handler(event)


@client.on(events.CallbackQuery(pattern=b'delete_sponsor_'))
async def delete_sponsor_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    try:
        sponsor_id = int(event.data.decode().split('_')[2])
    except:
        return

    sponsor = db.get_sponsor(sponsor_id)
    if not sponsor:
        await event.respond("❌ Спонсор не найден!")
        return

    db.delete_sponsor(sponsor_id)
    try:
        await event.delete()
    except:
        pass

    await event.respond(f"✅ Спонсор '{sponsor['name']}' удален!")
    await admin_sponsors_handler(event)


@client.on(events.CallbackQuery(pattern=b'add_sponsor'))
async def add_sponsor_handler(event):
    if event.sender_id != ADMIN_ID:
        return

    admin_states[event.sender_id] = {'state': AdminState.ADD_SPONSOR_NAME}
    try:
        await event.delete()
    except:
        pass

    await event.respond("📝 **ДОБАВЛЕНИЕ СПОНСОРА**\n\nВведите название спонсора:")


@client.on(events.NewMessage())
async def admin_message_handler(event):
    if event.sender_id != ADMIN_ID:
        return

    if event.sender_id not in admin_states:
        return

    text = event.message.message.strip()
    state_data = admin_states[event.sender_id]

    if isinstance(state_data, dict) and state_data['state'] == AdminState.ADD_SPONSOR_NAME:
        state_data['name'] = text
        state_data['state'] = AdminState.ADD_SPONSOR_LINK
        await event.respond("Введите ссылку на спонсора (URL):")

    elif isinstance(state_data, dict) and state_data['state'] == AdminState.ADD_SPONSOR_LINK:
        state_data['link'] = text
        state_data['state'] = AdminState.ADD_SPONSOR_CHANNEL
        await event.respond("Введите ID канала спонсора (например, @username или -1001234567890):")

    elif isinstance(state_data, dict) and state_data['state'] == AdminState.ADD_SPONSOR_CHANNEL:
        name = state_data.get('name', '')
        link = state_data.get('link', '')
        channel_id = text

        if not name or not link or not channel_id:
            await event.respond("❌ Ошибка: не все данные заполнены!")
            del admin_states[event.sender_id]
            return

        db.add_sponsor(name, link, channel_id)
        del admin_states[event.sender_id]

        await event.respond(f"✅ Спонсор '{name}' успешно добавлен!")
        await admin_sponsors_handler(event)

    elif state_data == AdminState.ADD_TASK_DESC:
        admin_states[event.sender_id] = {'state': AdminState.ADD_TASK_REWARD, 'description': text}
        await event.respond("Введите награду за задание (в звездах, число):")

    elif isinstance(state_data, dict) and state_data['state'] == AdminState.ADD_TASK_REWARD:
        try:
            reward = int(text)
            if reward <= 0:
                raise ValueError
        except:
            await event.respond("❌ Неверный формат! Введите целое положительное число:")
            return

        description = state_data.get('description', '')
        if not description:
            await event.respond("❌ Ошибка: описание задания потеряно!")
            del admin_states[event.sender_id]
            return

        db.add_task(description, reward)
        del admin_states[event.sender_id]

        await event.respond(f"✅ Задание успешно добавлено с наградой {reward}⭐!")
        await admin_tasks_handler(event)

    elif state_data == AdminState.ADD_PROMOCODE:
        admin_states[event.sender_id] = {'state': AdminState.ADD_PROMOCODE_REWARD, 'code': text.upper()}
        await event.respond("Введите награду за промокод (в звездах, число):")

    elif isinstance(state_data, dict) and state_data['state'] == AdminState.ADD_PROMOCODE_REWARD:
        try:
            reward = int(text)
            if reward <= 0:
                raise ValueError
        except:
            await event.respond("❌ Неверный формат! Введите целое положительное число:")
            return

        code = state_data.get('code', '')
        if not code:
            await event.respond("❌ Ошибка: код промокода потерян!")
            del admin_states[event.sender_id]
            return

        state_data['reward'] = reward
        state_data['state'] = AdminState.ADD_PROMOCODE_LIMIT
        await event.respond("Введите лимит использований промокода (число, по умолчанию 1):")

    elif isinstance(state_data, dict) and state_data['state'] == AdminState.ADD_PROMOCODE_LIMIT:
        try:
            limit = int(text) if text.strip() else 1
            if limit <= 0:
                raise ValueError
        except:
            await event.respond("❌ Неверный формат! Введите целое положительное число:")
            return

        code = state_data.get('code', '')
        reward = state_data.get('reward', 0)

        if not code or reward <= 0:
            await event.respond("❌ Ошибка: данные промокода потеряны!")
            del admin_states[event.sender_id]
            return

        db.add_promocode(code, reward, limit)
        del admin_states[event.sender_id]

        await event.respond(f"✅ Промокод '{code}' успешно добавлен с наградой {reward}⭐ и лимитом {limit}!")
        await admin_promocodes_handler(event)

    elif state_data == AdminState.SETTING_MIN_WITHDRAWAL:
        try:
            value = int(text)
            if value <= 0:
                raise ValueError
        except:
            await event.respond("❌ Неверный формат! Введите целое положительное число:")
            return

        db.update_setting('min_withdrawal', str(value))
        del admin_states[event.sender_id]

        await event.respond(f"✅ Минимальная сумма вывода установлена: {value}⭐")
        await admin_settings_handler(event)

    elif state_data == AdminState.SETTING_REFERRAL_REWARD:
        try:
            value = int(text)
            if value <= 0:
                raise ValueError
        except:
            await event.respond("❌ Неверный формат! Введите целое положительное число:")
            return

        db.update_setting('referral_reward', str(value))
        del admin_states[event.sender_id]

        await event.respond(f"✅ Награда за реферала установлена: {value}⭐")
        await admin_settings_handler(event)


@client.on(events.CallbackQuery(pattern=b'admin_tasks'))
async def admin_tasks_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    try:
        await event.delete()
    except:
        pass

    tasks = db.get_all_tasks()
    if not tasks:
        message = "📭 Список заданий пуст.\n\nНажмите '➕ Добавить задание' чтобы добавить новое задание."
    else:
        message = "📋 **УПРАВЛЕНИЕ ЗАДАНИЯМИ**\n\n"
        for task in tasks:
            status = "✅ Активно" if task['active'] else "❌ Неактивно"
            message += f"• #{task['id']}: {task['description'][:50]}...\n  Награда: {task['reward']}⭐\n  Статус: {status}\n\n"

    await event.respond(message, buttons=Keyboards.tasks_admin_menu(tasks))


@client.on(events.CallbackQuery(pattern=b'task_admin_'))
async def task_detail_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    try:
        task_id = int(event.data.decode().split('_')[2])
    except:
        return

    task = db.get_task(task_id)
    if not task:
        await event.respond("❌ Задание не найдено!")
        return

    try:
        await event.delete()
    except:
        pass

    status = "✅ Активно" if task['active'] else "❌ Неактивно"
    message = f"""
📝 **ИНФОРМАЦИЯ О ЗАДАНИИ**

🆔 **ID:** #{task['id']}
📋 **Описание:** {task['description']}
💰 **Награда:** {task['reward']}⭐
📊 **Статус:** {status}

Выберите действие:
"""
    await event.respond(message, buttons=Keyboards.task_detail_menu(task_id, task['active']))


@client.on(events.CallbackQuery(pattern=b'toggle_task_'))
async def toggle_task_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    try:
        task_id = int(event.data.decode().split('_')[2])
    except:
        return

    task = db.get_task(task_id)
    if not task:
        await event.respond("❌ Задание не найдено!")
        return

    new_status = not task['active']
    db.update_task_status(task_id, new_status)
    status_text = "активировано" if new_status else "деактивировано"

    try:
        await event.delete()
    except:
        pass

    await event.respond(f"✅ Задание #{task_id} {status_text}!")
    await admin_tasks_handler(event)


@client.on(events.CallbackQuery(pattern=b'delete_task_'))
async def delete_task_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    try:
        task_id = int(event.data.decode().split('_')[2])
    except:
        return

    task = db.get_task(task_id)
    if not task:
        await event.respond("❌ Задание не найдено!")
        return

    db.delete_task(task_id)
    try:
        await event.delete()
    except:
        pass

    await event.respond(f"✅ Задание #{task_id} удалено!")
    await admin_tasks_handler(event)


@client.on(events.CallbackQuery(pattern=b'add_task'))
async def add_task_handler(event):
    if event.sender_id != ADMIN_ID:
        return

    admin_states[event.sender_id] = AdminState.ADD_TASK_DESC
    try:
        await event.delete()
    except:
        pass

    await event.respond("📝 **ДОБАВЛЕНИЕ ЗАДАНИЯ**\n\nВведите описание задания:")


@client.on(events.CallbackQuery(pattern=b'admin_promocodes'))
async def admin_promocodes_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    try:
        await event.delete()
    except:
        pass

    promocodes = db.get_all_promocodes()
    if not promocodes:
        message = "📭 Список промокодов пуст.\n\nНажмите '➕ Добавить промокод' чтобы добавить новый промокод."
    else:
        message = "🎁 **УПРАВЛЕНИЕ ПРОМОКОДАМИ**\n\n"
        for promo in promocodes:
            status = "✅ Активен" if promo['active'] else "❌ Неактивен"
            message += f"• {promo['code']}\n  Награда: {promo['reward']}⭐\n  Использовано: {promo['times_used']}/{promo['usage_limit']}\n  Статус: {status}\n\n"

    await event.respond(message, buttons=Keyboards.promocodes_admin_menu(promocodes))


@client.on(events.CallbackQuery(pattern=b'promo_admin_'))
async def promocode_detail_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    try:
        code = event.data.decode().split('_')[2]
    except:
        return

    promo = db.get_promocode(code)
    if not promo:
        await event.respond("❌ Промокод не найден!")
        return

    try:
        await event.delete()
    except:
        pass

    status = "✅ Активен" if promo['active'] else "❌ Неактивен"
    message = f"""
🎫 **ИНФОРМАЦИЯ О ПРОМОКОДЕ**

🔤 **Код:** {promo['code']}
💰 **Награда:** {promo['reward']}⭐
📊 **Использовано:** {promo['times_used']}/{promo['usage_limit']}
📈 **Статус:** {status}

Выберите действие:
"""
    await event.respond(message, buttons=Keyboards.promocode_detail_menu(code, promo['active']))


@client.on(events.CallbackQuery(pattern=b'toggle_promo_'))
async def toggle_promocode_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    try:
        code = event.data.decode().split('_')[2]
    except:
        return

    promo = db.get_promocode(code)
    if not promo:
        await event.respond("❌ Промокод не найден!")
        return

    new_status = not promo['active']
    db.update_promocode_status(code, new_status)
    status_text = "активирован" if new_status else "деактивирован"

    try:
        await event.delete()
    except:
        pass

    await event.respond(f"✅ Промокод '{code}' {status_text}!")
    await admin_promocodes_handler(event)


@client.on(events.CallbackQuery(pattern=b'delete_promo_'))
async def delete_promocode_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    try:
        code = event.data.decode().split('_')[2]
    except:
        return

    promo = db.get_promocode(code)
    if not promo:
        await event.respond("❌ Промокод не найден!")
        return

    db.delete_promocode(code)
    try:
        await event.delete()
    except:
        pass

    await event.respond(f"✅ Промокод '{code}' удален!")
    await admin_promocodes_handler(event)


@client.on(events.CallbackQuery(pattern=b'add_promocode'))
async def add_promocode_handler(event):
    if event.sender_id != ADMIN_ID:
        return

    admin_states[event.sender_id] = AdminState.ADD_PROMOCODE
    try:
        await event.delete()
    except:
        pass

    await event.respond("🎁 **ДОБАВЛЕНИЕ ПРОМОКОДА**\n\nВведите код промокода (латинские буквы и цифры):")


@client.on(events.CallbackQuery(pattern=b'admin_settings'))
async def admin_settings_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    try:
        await event.delete()
    except:
        pass

    min_withdrawal = db.get_setting('min_withdrawal')
    referral_reward = db.get_setting('referral_reward')

    message = f"""
⚙️ **НАСТРОЙКИ БОТА**

💰 **Минимальная сумма вывода:** {min_withdrawal}⭐
👥 **Награда за реферала:** {referral_reward}⭐

Нажмите на настройку для изменения:
"""
    await event.respond(message, buttons=Keyboards.settings_menu())


@client.on(events.CallbackQuery(pattern=b'setting_min_withdrawal'))
async def setting_min_withdrawal_handler(event):
    if event.sender_id != ADMIN_ID:
        return

    admin_states[event.sender_id] = AdminState.SETTING_MIN_WITHDRAWAL
    try:
        await event.delete()
    except:
        pass

    current = db.get_setting('min_withdrawal')
    await event.respond(
        f"💰 **ИЗМЕНЕНИЕ МИНИМАЛЬНОЙ СУММЫ ВЫВОДА**\n\nТекущее значение: {current}⭐\nВведите новое значение (целое число):")


@client.on(events.CallbackQuery(pattern=b'setting_referral_reward'))
async def setting_referral_reward_handler(event):
    if event.sender_id != ADMIN_ID:
        return

    admin_states[event.sender_id] = AdminState.SETTING_REFERRAL_REWARD
    try:
        await event.delete()
    except:
        pass

    current = db.get_setting('referral_reward')
    await event.respond(
        f"👥 **ИЗМЕНЕНИЕ НАГРАДЫ ЗА РЕФЕРАЛА**\n\nТекущее значение: {current}⭐\nВведите новое значение (целое число):")


@client.on(events.CallbackQuery(pattern=b'admin_stats'))
async def admin_stats_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    try:
        await event.delete()
    except:
        pass

    stats = db.get_statistics()
    message = f"""
📊 **СТАТИСТИКА БОТА**

👥 **Всего пользователей:** {stats['total_users']}
✅ **Верифицированных:** {stats['verified_users']}
💰 **Всего звезд:** {stats['total_stars']}⭐

📋 **Активных спонсоров:** {stats['active_sponsors']}
📝 **Активных заданий:** {stats['active_tasks']}
🎁 **Активных промокодов:** {stats['active_promocodes']}

⏳ **Ожидающих выводов:** {stats['pending_withdrawals']}
"""
    await event.respond(message, buttons=Keyboards.admin_menu())


@client.on(events.CallbackQuery(pattern=b'admin_withdrawals'))
async def admin_withdrawals_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    try:
        await event.delete()
    except:
        pass

    await event.respond("💸 **УПРАВЛЕНИЕ ЗАЯВКАМИ НА ВЫВОД**\n\nВыберите тип заявок для просмотра:",
                        buttons=Keyboards.withdrawals_admin_menu())


@client.on(events.CallbackQuery(pattern=b'pending_withdrawals'))
async def pending_withdrawals_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    try:
        await event.delete()
    except:
        pass

    withdrawals = db.get_withdrawals('pending')
    if not withdrawals:
        await event.respond("📭 Нет ожидающих заявок на вывод.")
        return

    message = "⏳ **ОЖИДАЮЩИЕ ЗАЯВКИ НА ВЫВОД**\n\n"
    for w in withdrawals:
        user = db.get_user(w['user_id'])
        username = f"@{user['username']}" if user and user['username'] else f"ID: {w['user_id']}"
        message += f"🆔 **#{w['id']}** - {username}\n💰 {w['amount']}⭐\n📅 {w['created_at']}\n\n"

    await event.respond(message, buttons=Keyboards.withdrawals_admin_menu())


@client.on(events.NewMessage(pattern='/approve'))
async def approve_withdrawal_cmd(event):
    if event.sender_id != ADMIN_ID:
        return

    args = event.message.message.split()
    if len(args) < 2:
        await event.respond("❌ Используйте: /approve <id_заявки>")
        return

    try:
        withdrawal_id = int(args[1])
        db.update_withdrawal_status(withdrawal_id, 'completed')
        await event.respond(f"✅ Заявка #{withdrawal_id} одобрена!")
    except:
        await event.respond("❌ Ошибка при одобрении заявки!")


@client.on(events.NewMessage(pattern='/reject'))
async def reject_withdrawal_cmd(event):
    if event.sender_id != ADMIN_ID:
        return

    args = event.message.message.split()
    if len(args) < 2:
        await event.respond("❌ Используйте: /reject <id_заявки>")
        return

    try:
        withdrawal_id = int(args[1])
        db.update_withdrawal_status(withdrawal_id, 'rejected')
        await event.respond(f"❌ Заявка #{withdrawal_id} отклонена!")
    except:
        await event.respond("❌ Ошибка при отклонении заявки!")


async def main():
    me = await client.get_me()
    print(f"""
=========================================
🤖 БОТ ДЛЯ ЗАРАБОТКА TELEGRAM STARS
=========================================

⚙️  Конфигурация:
    • API ID: {API_ID}
    • API Hash: {API_HASH}
    • Бот: @{me.username}
    • Админ: {ADMIN_ID}

📊  База данных инициализирована
🔗  Бот запущен и готов к работе!
    """)

    await client.run_until_disconnected()


def signal_handler(signum, frame):
    print(f"\nПолучен сигнал {signum}. Корректное завершение...")
    client.disconnect()
    sys.exit(0)


if __name__ == '__main__':
    # Регистрация обработчиков сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Для Windows поддержка asyncio
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        client.loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n\n🛑 Бот остановлен пользователем")
    except Exception as e:
        print(f"\n\n❌ Ошибка при запуске бота: {e}")
        import traceback
        traceback.print_exc()
