from pathlib import Path


def test_private_container_contract():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text()
    entrypoint = (root / "worker_entrypoint.py").read_text()
    assert "playwright install --with-deps chromium" in dockerfile
    assert "COPY profile.json" not in dockerfile
    assert "COPY resume.pdf" not in dockerfile
    assert "VOLUME /workspace" in dockerfile
    assert 'host="0.0.0.0"' in entrypoint
    assert '"127.0.0.1", 8000' in entrypoint
    assert "APLYRA_CONTROL_TOKEN" in entrypoint
    assert "ollama serve" in entrypoint
    assert '["ollama", "pull", model]' in entrypoint
    assert "OLLAMA_MODELS=/workspace/ollama" in dockerfile
    assert "COPY --from=ollama /usr/lib/ollama /usr/local/lib/ollama" in dockerfile
