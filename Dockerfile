FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY bot ./bot
RUN pip install --no-cache-dir .

RUN addgroup --system bot && adduser --system --ingroup bot bot
USER bot

CMD ["python", "-m", "bot.main"]
