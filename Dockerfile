FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

# Создаем папку для базы данных
RUN mkdir -p /app/data

CMD ["python", "bot.py"]
