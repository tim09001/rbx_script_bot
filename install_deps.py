import subprocess
import sys

# Устанавливаем зависимости
subprocess.check_call([sys.executable, "-m", "pip", "install", "telethon", "requests"])

print("Зависимости установлены!")
