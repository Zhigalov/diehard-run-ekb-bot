import json
import zipfile

import pytest

from scripts import deploy


def test_package_excludes_local_secrets_and_dev_files(tmp_path):
    archive = tmp_path / "function.zip"
    deploy.package(archive)
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        assert "index.py" in names
        assert "bot/assets/welcome.jpg" in names
        assert all(name in {"index.py", "requirements.txt"} or name.startswith("bot/")
                   for name in names)
        assert not any(".env" in name or "__pycache__" in name for name in names)


@pytest.mark.parametrize("failure", ["candidate", "gateway", None])
def test_deploy_promotes_only_verified_version_and_restores_on_failure(monkeypatch, failure):
    calls = []
    config = {"function_id": "fn", "folder_id": "folder", "gateway_id": "gw"}

    def fake_yc(*args, **kwargs):
        calls.append(args)
        if args[:3] == ("serverless", "function", "get"):
            return {"id": "fn", "folder_id": "folder"}
        if args[:4] == ("serverless", "function", "version", "get-by-tag"):
            return {"id": "previous", "function_id": "fn"}
        if args[:3] == ("serverless", "api-gateway", "get"):
            return {"folder_id": "folder", "domain": "gateway.example"}
        if args[:3] == ("serverless", "api-gateway", "get-spec"):
            return {"openapi_spec": json.dumps(deploy.spec("fn", "sa"))}
        if args[:4] == ("serverless", "function", "version", "get"):
            return {"id": "candidate", "function_id": "fn"}
        return {}

    def fail():
        raise RuntimeError("test failure")

    monkeypatch.setattr(deploy, "yc", fake_yc)
    monkeypatch.setattr(deploy, "secrets_for", lambda version: {"WEBHOOK_SECRET": "test"})
    monkeypatch.setattr(deploy, "smoke_function",
                        lambda *args: fail() if failure == "candidate" else None)
    monkeypatch.setattr(deploy, "smoke_gateway",
                        lambda *args: fail() if failure == "gateway" else None)
    if failure:
        with pytest.raises(RuntimeError):
            deploy.deploy(config, rollback="candidate")
    else:
        deploy.deploy(config, rollback="candidate")
    promotions = [args[4] for args in calls if args[:4] == (
        "serverless", "function", "version", "set-tag") and args[-1] == "production"]
    assert promotions == {"candidate": [], "gateway": ["candidate", "previous"],
                          None: ["candidate"]}[failure]
