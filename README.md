# diehard-run-ekb-bot

Telegram-бот бегового чата Diehard в Екатеринбурге. Первая версия приветствует
пользователя после команды `/start`.

## Запуск в Yandex Cloud Functions

Основной способ запуска — Telegram webhook, который вызывает Python-функцию.
Точка входа функции находится в `index.handler`.

1. Создайте ZIP-архив для загрузки в Cloud Functions:

   ```bash
   zip -r function.zip index.py requirements.txt bot \
     -x '*__pycache__*' '*.pyc'
   ```

2. Создайте функцию с параметрами:

   - среда выполнения: Python 3.12;
   - точка входа: `index.handler`;
   - память: 256 МБ;
   - таймаут: 10 секунд;
   - публичная функция: включена;
   - подключение к пользовательской VPC: не требуется.

3. Добавьте переменные окружения функции:

   - `BOT_TOKEN` — токен от [@BotFather](https://t.me/BotFather);
   - `WEBHOOK_SECRET` — случайная строка для проверки запросов Telegram.

4. После создания версии функции скопируйте HTTPS-адрес вида
   `https://functions.yandexcloud.net/<function-id>`.

5. Создайте локальный `.env` по примеру, заполните три значения и зарегистрируйте
   webhook с компьютера, на котором доступен Telegram API:

   ```bash
   cp .env.example .env
   set -a
   source .env
   set +a
   python -m scripts.set_webhook
   ```

6. Откройте бота в Telegram и отправьте `/start`.

Файл `.env` исключён из Git и Docker-контекста. Не публикуйте токен бота,
webhook-секрет и содержимое `.env`.

## Локальный запуск через Docker

Этот режим использует long polling и нужен только для разработки в сети, где
доступен `api.telegram.org`.

1. Создайте и заполните `.env`:

   ```bash
   cp .env.example .env
   ```

2. Запустите бота:

   ```bash
   docker compose up --build -d
   ```

3. Откройте бота в Telegram и нажмите «Начать».

Посмотреть журнал работы:

```bash
docker compose logs -f bot
```

Остановить бота:

```bash
docker compose down
```

## Разработка без Docker

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
BOT_TOKEN=your-token python -m bot.main
```
