"""Create an isolated Yandex scope from an existing bot; does not switch Cloudflare."""

import argparse
import json
import tempfile
from pathlib import Path

from scripts.deploy import create_version, package, secrets_for, smoke_function, smoke_gateway, spec, yc


def ensure(group: tuple[str, ...], name: str, scope: list[str], extra: list[str] | None = None):
    found = [x for x in yc(*group, "list", *scope) if x.get("name") == name]
    if len(found) > 1:
        raise RuntimeError(f"Ambiguous resource name: {name}")
    if found:
        return found[0]
    return yc(*group, "create", "--name", name, *scope, *(extra or []))


def bootstrap(cloud_id: str, source_function_id: str, name: str) -> dict:
    source = yc("serverless", "function", "version", "get-by-tag",
                "--function-id", source_function_id, "--tag", "$latest")
    folder = ensure(("resource-manager", "folder"), name, ["--cloud-id", cloud_id])
    scope = ["--folder-id", folder["id"]]
    print(f"Folder: {folder['id']}", flush=True)
    account = ensure(("iam", "service-account"), "bot-runtime", scope)
    logs = ensure(("logging", "group"), "bot", scope, ["--retention-period", "168h"])
    function = ensure(("serverless", "function"), name, scope)
    existing = [x for x in yc("lockbox", "secret", "list", *scope) if x["name"] == "bot"]
    if len(existing) > 1:
        raise RuntimeError("Ambiguous bot secret")
    if existing:
        secret = yc("lockbox", "secret", "get", existing[0]["id"])
    else:
        credentials = secrets_for(source)
        secret = yc("lockbox", "secret", "create", "--name", "bot", *scope,
                    "--deletion-protection", "--payload", "-",
                    stdin=json.dumps([{"key": k, "text_value": credentials[k]}
                                      for k in ("BOT_TOKEN", "WEBHOOK_SECRET")]))
    secret_version = secret["current_version"]["id"]
    yc("lockbox", "secret", "add-access-binding", secret["id"],
       "--role", "lockbox.payloadViewer", "--service-account-id", account["id"])
    yc("serverless", "function", "add-access-binding", function["id"],
       "--role", "functions.functionInvoker", "--service-account-id", account["id"])
    config = {"cloud_id": cloud_id, "folder_id": folder["id"], "function_id": function["id"],
              "service_account_id": account["id"], "log_group_id": logs["id"],
              "secret_id": secret["id"]}
    source["secrets"] = [{"id": secret["id"], "version_id": secret_version,
                          "key": key, "environment_variable": key}
                         for key in ("BOT_TOKEN", "WEBHOOK_SECRET")]
    # Never rerun bootstrap against an already live production function.
    versions = yc("serverless", "function", "version", "list", "--function-id", function["id"])
    production = [v for v in versions if "production" in v.get("tags", [])]
    with tempfile.TemporaryDirectory(prefix="diehard-bootstrap-") as temporary:
        if not production:
            archive = Path(temporary) / "function.zip"
            package(archive)
            candidate = create_version(config, source, archive)
            tag = next(t for t in candidate["tags"] if t.startswith("candidate-"))
            credentials = secrets_for(candidate)
            smoke_function(function["id"], tag, credentials["WEBHOOK_SECRET"])
            yc("serverless", "function", "version", "set-tag", candidate["id"],
               "--tag", "production")
        else:
            credentials = secrets_for(production[0])
        spec_path = Path(temporary) / "gateway.json"
        spec_path.write_text(json.dumps(spec(function["id"], account["id"])))
        gateway = ensure(("serverless", "api-gateway"), name, scope,
                         ["--spec", str(spec_path), "--log-group-id", logs["id"],
                          "--execution-timeout", "40s"])
    config["gateway_id"] = gateway["id"]
    config["gateway_url"] = f"https://{gateway['domain']}/webhook"
    smoke_gateway(config["gateway_url"], credentials["WEBHOOK_SECRET"])
    return config


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cloud-id", required=True)
    parser.add_argument("--source-function-id", required=True)
    parser.add_argument("--name", default="diehard-run-ekb-bot")
    args = parser.parse_args()
    # Output contains only resource IDs and the public gateway URL.
    print(json.dumps(bootstrap(args.cloud_id, args.source_function_id, args.name), indent=2))
