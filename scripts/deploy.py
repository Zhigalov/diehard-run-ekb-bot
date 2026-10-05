"""Deploy a tested candidate, then promote the production tag. No secrets on disk."""

import argparse
import json
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "deploy/production.json"


def yc(*args: str, stdin: str | None = None):
    result = subprocess.run(
        ["yc", *args, "--format", "json"], input=stdin, capture_output=True, text=True,
        timeout=600,
    )
    if result.returncode:
        # CLI errors can contain secrets, payloads, or credential-bearing URLs.
        raise RuntimeError(f"Yandex CLI failed: {' '.join(args[:3])} (exit {result.returncode})")
    return json.loads(result.stdout) if result.stdout.strip() else {}


def package(destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in [ROOT / "index.py", ROOT / "requirements.txt", *(ROOT / "bot").rglob("*")]:
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                archive.write(path, path.relative_to(ROOT))


def secrets_for(version: dict) -> dict[str, str]:
    values = {}
    for reference in version["secrets"]:
        payload = yc("lockbox", "payload", "get", reference["id"],
                     "--version-id", reference["version_id"])
        entry = next(x for x in payload["entries"] if x["key"] == reference["key"])
        values[reference["environment_variable"]] = entry["text_value"]
    return values


def smoke_function(function_id: str, tag: str, secret: str) -> None:
    for supplied, expected in [("invalid-diagnostic-secret", 401), (secret, 200)]:
        event = {"headers": {"X-Telegram-Bot-Api-Secret-Token": supplied},
                 "body": '{"update_id":0}'}
        response = yc("serverless", "function", "invoke", function_id, "--tag", tag,
                      "--data-stdin", stdin=json.dumps(event))
        if response.get("statusCode") != expected:
            raise RuntimeError(f"Candidate smoke check failed (expected {expected})")


def smoke_gateway(url: str, secret: str) -> None:
    for supplied, expected in [("invalid-diagnostic-secret", 401), (secret, 200)]:
        request = urllib.request.Request(
            url, data=b'{"update_id":0}',
            headers={"Content-Type": "application/json", "User-Agent": "curl/8.7.1",
                     "X-Telegram-Bot-Api-Secret-Token": supplied},
        )
        try:
            response = urllib.request.urlopen(request, timeout=40)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            if response.status != expected:
                raise RuntimeError(f"Gateway check failed: HTTP {response.status}")


def spec(function_id: str, service_account_id: str) -> dict:
    return {
        "openapi": "3.0.0", "info": {"title": "diehard-run-ekb-bot", "version": "1.0.0"},
        "paths": {"/webhook": {"post": {
            "operationId": "telegramWebhook",
            "responses": {"200": {"description": "OK"}},
            "x-yc-apigateway-integration": {
                "type": "cloud_functions", "function_id": function_id,
                "tag": "production", "service_account_id": service_account_id,
                "payload_format_version": "1.0",
            },
        }}},
    }


def create_version(config: dict, previous: dict, source: Path) -> dict:
    # Preserve deployed env and pinned Lockbox references. Never load a local .env.
    args = ["serverless", "function", "version", "create",
            "--function-id", config["function_id"], "--runtime", "python312",
            "--entrypoint", config.get("entrypoint", "index.handler"), "--memory", "512MB",
            "--execution-timeout", config.get("execution_timeout", "30s"), "--concurrency", "1",
            "--service-account-id", config["service_account_id"],
            "--log-group-id", config["log_group_id"], "--min-log-level", "info",
            "--source-path", str(source), "--tags", "candidate-" + uuid.uuid4().hex[:12]]
    environment = {**previous.get("environment", {}), **config.get("environment", {})}
    # Refuse to put literal credentials into process arguments.
    if any("TOKEN" in key or "SECRET" in key for key in environment):
        raise RuntimeError("Move secret environment values to Lockbox before deployment")
    if any("," in str(value) for value in environment.values()):
        raise RuntimeError("Environment values containing commas require explicit CLI escaping")
    if environment:
        args += ["--environment", ",".join(f"{k}={v}" for k, v in environment.items())]
    for reference in previous["secrets"]:
        args += ["--secret", ",".join(f"{key}={reference[field]}" for key, field in [
            ("id", "id"), ("version-id", "version_id"), ("key", "key"),
            ("environment-variable", "environment_variable"),
        ])]
    return yc(*args)


def deploy(config: dict, rollback: str | None = None) -> None:
    function = yc("serverless", "function", "get", config["function_id"])
    if function["folder_id"] != config["folder_id"]:
        raise RuntimeError("Function is outside the configured deployment folder")
    previous = yc("serverless", "function", "version", "get-by-tag",
                  "--function-id", config["function_id"], "--tag", "production")
    gateway = yc("serverless", "api-gateway", "get", config["gateway_id"])
    if gateway["folder_id"] != config["folder_id"]:
        raise RuntimeError("Gateway is outside the configured deployment folder")
    deployed_spec = yc("serverless", "api-gateway", "get-spec", config["gateway_id"])
    # Our provisioned spec is JSON (valid OpenAPI/YAML), so no YAML dependency is needed.
    integration = json.loads(deployed_spec["openapi_spec"])["paths"]["/webhook"]["post"][
        "x-yc-apigateway-integration"]
    if integration["tag"] != "production" or integration["function_id"] != function["id"]:
        raise RuntimeError("Gateway must point at this function's production tag")
    if rollback:
        candidate = yc("serverless", "function", "version", "get", rollback)
        if candidate["function_id"] != function["id"]:
            raise RuntimeError("Rollback version belongs to another function")
        tag = "rollback-" + uuid.uuid4().hex[:12]
        yc("serverless", "function", "version", "set-tag", candidate["id"], "--tag", tag)
    else:
        for command in [[sys.executable, "-m", "ruff", "check", "."],
                        [sys.executable, "-m", "pytest", "-q"], ["git", "diff", "--check"]]:
            subprocess.run(command, cwd=ROOT, check=True)
        with tempfile.TemporaryDirectory(prefix="diehard-deploy-") as temporary:
            archive = Path(temporary) / "function.zip"
            package(archive)
            print("Building candidate; production is unchanged", flush=True)
            candidate = create_version(config, previous, archive)
        tag = next(tag for tag in candidate["tags"] if tag.startswith("candidate-"))
    credentials = secrets_for(candidate)
    smoke_function(function["id"], tag, credentials["WEBHOOK_SECRET"])
    print(f"Candidate verified: {candidate['id']}; rollback: {previous['id']}", flush=True)
    try:
        yc("serverless", "function", "version", "set-tag", candidate["id"],
           "--tag", "production")
        smoke_gateway(f"https://{gateway['domain']}/webhook", credentials["WEBHOOK_SECRET"])
    except Exception:
        yc("serverless", "function", "version", "set-tag", previous["id"],
           "--tag", "production")
        print(f"Restored production version {previous['id']}", flush=True)
        raise
    print(f"Deployed {candidate['id']} to folder {config['folder_id']}")


def deploy_reminders(config: dict) -> None:
    function_id = config["reminder_function_id"]
    function = yc("serverless", "function", "get", function_id)
    if function["folder_id"] != config["folder_id"]:
        raise RuntimeError("Reminder function is outside the configured folder")
    # Same pinned secrets and runtime env as the live bot. No local .env involved.
    source = yc("serverless", "function", "version", "get-by-tag",
                "--function-id", config["function_id"], "--tag", "production")
    target = {**config, "function_id": function_id, "entrypoint": "bot.reminders.handler",
              "execution_timeout": "90s"}
    with tempfile.TemporaryDirectory(prefix="diehard-reminders-") as temporary:
        archive = Path(temporary) / "function.zip"
        package(archive)
        candidate = create_version(target, source, archive)
    tag = next(t for t in candidate["tags"] if t.startswith("candidate-"))
    response = yc("serverless", "function", "invoke", function_id, "--tag", tag,
                  "--data-stdin", stdin=json.dumps({"healthcheck": True}))
    if response.get("statusCode") != 200:
        raise RuntimeError("Reminder storage health check failed; production unchanged")
    yc("serverless", "function", "version", "set-tag", candidate["id"], "--tag", "production")
    print(f"Deployed reminder worker {candidate['id']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rollback", metavar="VERSION_ID")
    args = parser.parse_args()
    try:
        deploy(json.loads(CONFIG.read_text()), args.rollback)
        config = json.loads(CONFIG.read_text())
        if not args.rollback and config.get("reminder_function_id"):
            deploy_reminders(config)
    except Exception as error:
        # Never print raw network/subprocess exception text.
        print(f"Deployment failed ({type(error).__name__}). Production tag was not intentionally "
              "changed unless promotion had started; inspect its current value before retrying.",
              file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
