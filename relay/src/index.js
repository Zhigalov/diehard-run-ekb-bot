const TELEGRAM_API_ORIGIN = "https://api.telegram.org";

function constantTimeEqual(left, right) {
  const encoder = new TextEncoder();
  const leftBytes = encoder.encode(left);
  const rightBytes = encoder.encode(right);
  const length = Math.max(leftBytes.length, rightBytes.length);
  let difference = leftBytes.length ^ rightBytes.length;

  for (let index = 0; index < length; index += 1) {
    difference |= (leftBytes[index] ?? 0) ^ (rightBytes[index] ?? 0);
  }

  return difference === 0;
}

function plainText(message, status) {
  return new Response(message, {
    status,
    headers: { "content-type": "text/plain; charset=utf-8" },
  });
}

async function forwardWebhook(request, env) {
  if (request.method !== "POST") {
    return plainText("Method Not Allowed", 405);
  }

  const receivedSecret = request.headers.get("x-telegram-bot-api-secret-token") ?? "";
  if (!constantTimeEqual(receivedSecret, env.WEBHOOK_SECRET)) {
    return plainText("Unauthorized", 401);
  }

  const headers = new Headers();
  headers.set("content-type", request.headers.get("content-type") ?? "application/json");
  headers.set("x-telegram-bot-api-secret-token", env.WEBHOOK_SECRET);

  return fetch(env.UPSTREAM_URL, {
    method: "POST",
    headers,
    body: await request.arrayBuffer(),
  });
}

async function forwardTelegramApi(request, env, url) {
  const botPrefix = `/bot${env.BOT_TOKEN}/`;
  const filePrefix = `/file/bot${env.BOT_TOKEN}/`;
  if (!url.pathname.startsWith(botPrefix) && !url.pathname.startsWith(filePrefix)) {
    return plainText("Not Found", 404);
  }

  const target = new URL(url.pathname + url.search, TELEGRAM_API_ORIGIN);
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers.set("content-type", contentType);
  }

  const init = {
    method: request.method,
    headers,
    redirect: "manual",
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }

  return fetch(target, init);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/webhook") {
      return forwardWebhook(request, env);
    }

    return forwardTelegramApi(request, env, url);
  },
};
