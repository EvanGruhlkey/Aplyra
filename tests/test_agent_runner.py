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
    llm = make_llm()
    assert llm.model == "qwen3:4b"
    assert llm.ollama_options["think"] is False
    assert llm.ollama_options["num_gpu"] == 0
