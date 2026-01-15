import os
import asyncio
from main import bot, BOT_TOKEN

async def start():
    print("🚀 Запускаем бота...")
    await bot.start(bot_token=BOT_TOKEN)
    print("✅ Бот запущен!")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(start())
