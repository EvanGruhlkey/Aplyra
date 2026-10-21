import json

import pytest

from agent import is_mock_url, load_profile, require_submission_authorization


def test_real_site_needs_explicit_authorization():
    assert is_mock_url("http://localhost:8000/apply")
    assert is_mock_url("http://127.0.0.1:8000/apply")
    assert not is_mock_url("https://jobs.example.com/apply")
    with pytest.raises(ValueError, match="authorize"):
        require_submission_authorization("https://jobs.example.com/apply", False)
    require_submission_authorization("https://jobs.example.com/apply", True)


def test_profile_requires_real_contact_and_resume(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps({"contact": {"full_name": "", "email": ""}}))
    with pytest.raises(ValueError, match="contact"):
        load_profile(path, tmp_path / "resume.pdf")
