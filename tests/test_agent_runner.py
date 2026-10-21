import pytest

from agent import run_application


def test_runner_requires_exact_authorized_url(tmp_path):
    with pytest.raises(ValueError, match="exact"):
        run_application("https://example.com/apply", tmp_path / "profile.json", tmp_path / "resume.pdf", tmp_path / "runs", "https://other.com/apply", True)


def test_runner_validates_files_before_browser(tmp_path):
    with pytest.raises((ValueError, FileNotFoundError)):
        run_application("http://localhost:8000/apply", tmp_path / "missing.json", tmp_path / "missing.pdf", tmp_path / "runs", None, True)
