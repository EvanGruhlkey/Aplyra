import pytest

from agent import make_llm, run_application


def test_runner_requires_exact_authorized_url(tmp_path):
    with pytest.raises(ValueError, match="exact"):
        run_application("https://example.com/apply", tmp_path / "profile.json", tmp_path / "resume.pdf", tmp_path / "runs", "https://other.com/apply", True)


def test_runner_validates_files_before_browser(tmp_path):
    with pytest.raises((ValueError, FileNotFoundError)):
        run_application("http://localhost:8000/apply", tmp_path / "missing.json", tmp_path / "missing.pdf", tmp_path / "runs", None, True)


def test_ollama_uses_non_thinking_cpu_mode(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:4b")
    monkeypatch.setenv("OLLAMA_NUM_GPU", "0")
    llm = make_llm()
    assert llm.model == "qwen3:4b"
    assert llm.ollama_options["think"] is False
    assert llm.ollama_options["num_gpu"] == 0


def test_ollama_autodetects_gpu_by_default(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.delenv("OLLAMA_NUM_GPU", raising=False)
    assert "num_gpu" not in make_llm().ollama_options


def test_self_hosted_browser_model_uses_configured_endpoint(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "self_hosted")
    monkeypatch.setenv("SELF_HOSTED_BASE_URL", "http://model:8001/v1")
    llm = make_llm()
    assert llm.model == "browser-use/bu-30b-a3b-preview"
    assert str(llm.base_url) == "http://model:8001/v1"
    assert llm.dont_force_structured_output is True


def test_self_hosted_model_requires_endpoint(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "self_hosted")
    monkeypatch.delenv("SELF_HOSTED_BASE_URL", raising=False)
    with pytest.raises(ValueError, match="SELF_HOSTED_BASE_URL"):
        make_llm()
