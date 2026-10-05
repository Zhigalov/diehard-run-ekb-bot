"""Provision private reminder resources; enable the timer only after deployment."""

import argparse
import json
import subprocess
from urllib.parse import parse_qs, urlsplit

from scripts.bootstrap_scope import ensure
from scripts.deploy import CONFIG, yc

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscribers (
    chat_id Int64 NOT NULL,
    active Bool,
    subscribed_at Int64,
    sent_week Utf8,
    lease_until Int64,
    owner Utf8,
    next_attempt Int64,
    PRIMARY KEY (chat_id)
);
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-timer", action="store_true")
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text())
    scope = ["--folder-id", config["folder_id"]]
    if args.enable_timer:
        # Readiness check: never enable a schedule against an undeployed worker.
        result = yc("serverless", "function", "invoke", config["reminder_function_id"],
                    "--tag", "production", "--data-stdin", stdin='{"healthcheck":true}')
        if result.get("statusCode") != 200:
            raise RuntimeError("Reminder function is not ready")
        existing = [t for t in yc("serverless", "trigger", "list", *scope)
                    if t["name"] == "friday-registration"]
        if existing:
            print("Timer already exists; inspect before changing its schedule")
            return
        trigger = yc("serverless", "trigger", "create", "timer", "--name",
                     "friday-registration", *scope, "--cron-expression", "* 9 ? * FRI *",
                     "--invoke-function-id", config["reminder_function_id"],
                     "--invoke-function-tag", "production",
                     "--invoke-function-service-account-id", config["service_account_id"],
                     "--retry-attempts", "3", "--retry-interval", "60s")
        print(json.dumps({"trigger_id": trigger["id"], "schedule": "Friday 12:00 MSK"}))
        return

    database = ensure(("ydb", "database"), "bot-subscribers", scope,
                      ["--serverless", "--location", "ru-central1", "--deletion-protection",
                       "--sls-enable-throttling-rcu", "--sls-throttling-rcu", "10",
                       "--sls-provisioned-rcu", "0", "--sls-storage-size", "1GB"])
    database = yc("ydb", "database", "get", database["id"])
    yc("ydb", "database", "add-access-binding", database["id"], "--role", "ydb.editor",
       "--service-account-id", config["service_account_id"])
    function = ensure(("serverless", "function"), "registration-reminders", scope)
    yc("serverless", "function", "add-access-binding", function["id"],
       "--role", "functions.functionInvoker", "--service-account-id", config["service_account_id"])
    url = urlsplit(database["endpoint"])
    endpoint = f"{url.scheme}://{url.netloc}"
    path = parse_qs(url.query)["database"][0]
    # IAM token stays in memory, never on disk, argv, or stdout.
    import ydb

    auth = subprocess.run(["yc", "iam", "create-token"], capture_output=True, text=True)
    if auth.returncode:
        raise RuntimeError("Cannot obtain deployment IAM token")
    with ydb.Driver(endpoint=endpoint, database=path,
                    credentials=ydb.AccessTokenCredentials(auth.stdout.strip())) as driver:
        driver.wait(timeout=10, fail_fast=True)
        with ydb.SessionPool(driver) as pool:
            pool.retry_operation_sync(lambda session: session.execute_scheme(SCHEMA))
    print(json.dumps({"reminder_function_id": function["id"], "database_id": database["id"],
                      "environment": {"YDB_ENDPOINT": endpoint, "YDB_DATABASE": path}}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Reminder setup failed ({type(error).__name__}); inspect resource status")
        raise SystemExit(1) from None
