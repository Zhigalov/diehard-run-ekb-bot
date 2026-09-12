# diehard-run-ekb-bot

Telegram-бот бегового чата Diehard в Екатеринбурге. Первая версия приветствует
пользователя после команды `/start`.

## Что понадобится

- токен бота от [@BotFather](https://t.me/BotFather);
- Docker с поддержкой Docker Compose.

## Запуск

1. Создайте локальный файл настроек:

   ```bash
   cp .env.example .env
   ```

2. Вставьте токен от BotFather в `BOT_TOKEN` внутри `.env`.
3. Запустите бота:

   ```bash
   docker compose up --build -d
   ```

4. Откройте бота в Telegram и нажмите «Начать».

Посмотреть журнал работы:

```bash
docker compose logs -f bot
```

Остановить бота:

```bash
docker compose down
```

Файл `.env` исключён из Git и Docker-контекста. Не публикуйте токен бота и не
добавляйте его в исходный код.

## Разработка без Docker

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
BOT_TOKEN=your-token python -m bot.main
```
