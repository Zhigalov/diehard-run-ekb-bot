# diehard-run-ekb-bot

Telegram-бот бегового чата Diehard в Екатеринбурге. Первая версия приветствует
пользователя после команды `/start`.

## Запуск через Cloudflare Relay и Yandex Cloud Functions

Из-за недоступности Telegram API из Yandex Cloud запросы идут через небольшой
Cloudflare Worker в обе стороны:

```text
Telegram -> Cloudflare Worker -> API Gateway -> Cloud Function
Cloud Function -> Cloudflare Worker -> Telegram Bot API
```

Worker не хранит сообщения. Он проверяет webhook-секрет, пересылает обновление
функции и разрешает Bot API-запросы только для токена этого бота.

### 1. Yandex Cloud Function

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

4. Создайте API Gateway с POST-маршрутом `/webhook`, интегрированным с функцией,
   и сохраните адрес вида `https://<gateway>.apigw.yandexcloud.net/webhook`.

### 2. Cloudflare Worker

Для деплоя нужен Node.js. Из корня репозитория выполните:

```bash
cd relay
npx wrangler login
npx wrangler secret put BOT_TOKEN
npx wrangler secret put WEBHOOK_SECRET
npx wrangler secret put UPSTREAM_URL
npx wrangler deploy
```

Wrangler запросит значения интерактивно:

- `BOT_TOKEN` — тот же токен BotFather, который задан в функции;
- `WEBHOOK_SECRET` — тот же секрет, который задан в функции;
- `UPSTREAM_URL` — полный адрес API Gateway с `/webhook`.

После деплоя сохраните адрес Worker вида
`https://diehard-run-ekb-bot-relay.<account>.workers.dev`.

### 3. Подключение функции к relay

Создайте новую версию функции на Python 3.12 и добавьте к существующим
переменным окружения:

```text
TELEGRAM_API_BASE_URL=https://diehard-run-ekb-bot-relay.<account>.workers.dev
```

Пересоберите ZIP перед загрузкой, чтобы в нём был обновлённый `index.py`:

```bash
zip -r function.zip index.py requirements.txt bot \
  -x '*__pycache__*' '*.pyc'
```

### 4. Регистрация webhook

В локальном `.env` укажите адрес Worker:

```text
WEBHOOK_URL=https://diehard-run-ekb-bot-relay.<account>.workers.dev/webhook
```

Затем зарегистрируйте webhook с компьютера, на котором доступен Telegram API:

```bash
set -a
source .env
set +a
python -m scripts.set_webhook
```

Откройте бота в Telegram и отправьте новый `/start` после регистрации webhook.

## Допуск в группу после принятия правил

Бот обрабатывает заявки на вступление (`chat_join_request`). До подтверждения
правил пользователь остаётся в списке заявок и не является участником группы.

Настройка тестовой группы:

1. Добавьте бота в группу как администратора.
2. Выдайте ему право приглашать пользователей — оно требуется для одобрения
   заявок.
3. Создайте ссылку-приглашение с включённой опцией запроса одобрения
   администратором.
4. Отзовите обычные ссылки-приглашения, позволяющие войти без заявки.
5. Если у группы есть публичный username, убедитесь, что через него нельзя
   вступить напрямую. Для строгого режима на время MVP сделайте группу частной.

После перехода по ссылке пользователь нажимает «Подать заявку». Telegram даёт
боту временную возможность написать заявителю в личный чат. Бот отправляет
правила и персональную кнопку подтверждения, затем предлагает простую
тематическую каптчу. Только после правильного ответа бот одобряет заявку.

Каптча и её кнопки подписаны webhook-секретом и привязаны к Telegram ID
заявителя и конкретной группе. Неверный ответ можно исправить повторным
нажатием; лимит попыток в этой базовой версии не используется.

После добавления этого сценария webhook нужно зарегистрировать повторно: список
`allowed_updates` должен включать `chat_join_request` и `callback_query`.

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
