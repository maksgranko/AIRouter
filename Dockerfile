FROM python:3.11-slim

# Установим рабочую директорию
WORKDIR /app

# Копируем только файл зависимостей сначала, для кэширования pip install
COPY requirements.txt ./

# Устанавливаем зависимости
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Копируем остальные файлы приложения
COPY . .

# Открываем порт
EXPOSE 8000

# Команда запуска приложения
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
