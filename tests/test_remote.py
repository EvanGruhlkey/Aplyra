import pytest

from remote import require_exact_authorization, deploy_commands


def test_exact_authorization():
    require_exact_authorization("http://localhost:8000/apply", None)
    with pytest.raises(ValueError, match="exact"):
        require_exact_authorization("https://jobs.example.com/apply", "https://other.example.com/apply")
    require_exact_authorization("https://jobs.example.com/apply", "https://jobs.example.com/apply")


def test_deploy_commands_reuse_existing_resources():
    commands = deploy_commands("aplyra-demo", "dfw", app_exists=True, volume_exists=True)
    assert not any(command[:2] == ["apps", "create"] for command in commands)
    assert not any(command[:2] == ["volumes", "create"] for command in commands)
    assert commands[-1] == ["deploy", "--app", "aplyra-demo", "--ha=false"]
    fresh = deploy_commands("aplyra-demo", "dfw", app_exists=False, volume_exists=False)
    assert ["apps", "create", "aplyra-demo"] in fresh
    assert ["volumes", "create", "data", "--size", "3", "--region", "dfw", "--app", "aplyra-demo", "--yes"] in fresh
