"""Apply through Browser Use with a local profile."""

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from dotenv import load_dotenv


def is_mock_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"} and parsed.path == "/apply"


def require_submission_authorization(url: str, authorized: bool) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Provide a valid http or https application URL")
    if not is_mock_url(url) and not authorized:
        raise ValueError("Real sites require --authorize-submit before the browser starts")


def load_profile(path: Path, resume_path: Path) -> dict:
    profile = json.loads(path.read_text(encoding="utf-8"))
    contact = profile.get("contact", {})
    if not all(contact.get(key) for key in ("full_name", "email", "phone")):
        raise ValueError("Complete contact.full_name, contact.email, and contact.phone in profile.json")
    if not profile.get("education") or not profile.get("work_experience") or not profile.get("answers", {}).get("work_authorization") or not profile.get("answers", {}).get("why_interested"):
        raise ValueError("Complete education, work_experience, and common answers in profile.json")
    if not resume_path.is_file() or not resume_path.read_bytes().startswith(b"%PDF-"):
        raise ValueError(f"Provide a PDF resume at {resume_path}")
    return profile


def make_llm():
    from browser_use import ChatOllama, ChatOpenAI

    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    if provider == "ollama":
        options = {"think": False, "num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "16384"))}
        if os.getenv("OLLAMA_NUM_GPU") is not None:
            options["num_gpu"] = int(os.environ["OLLAMA_NUM_GPU"])
        return ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "qwen3:8b"),
            host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            timeout=180,
            ollama_options=options,
        )
    if provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("Set OPENAI_API_KEY for the API provider")
        return ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), api_key=os.environ["OPENAI_API_KEY"], base_url=os.getenv("OPENAI_BASE_URL") or None)
    if provider == "self_hosted":
        base_url = os.getenv("SELF_HOSTED_BASE_URL")
        if not base_url:
            raise ValueError("Set SELF_HOSTED_BASE_URL for the self-hosted model")
        return ChatOpenAI(
            model=os.getenv("SELF_HOSTED_MODEL", "browser-use/bu-30b-a3b-preview"),
            base_url=base_url,
            api_key=os.getenv("SELF_HOSTED_API_KEY", "not-needed"),
            temperature=0.6,
            top_p=0.95,
            dont_force_structured_output=True,
        )
    raise ValueError("LLM_PROVIDER must be ollama, self_hosted, or openai")


def build_task(url: str, profile: dict, resume_path: Path) -> str:
    return (
        f"Open {url} and complete the job application. Use the visible page and your built-in browser actions to discover fields and navigate; do not assume selectors. "
        f"Candidate profile (JSON): {json.dumps(profile, ensure_ascii=False)}. "
        f"Upload the PDF at {resume_path.resolve()} using the upload_file action. "
        "For every click, input, and upload, use the bracketed element index shown in the latest browser state. Never use index 0 unless it is explicitly shown there. If an index fails, inspect the page again before retrying. "
        "Use only facts in the profile. For an unfamiliar question or missing answer, stop and explain what information is needed. "
        "If you encounter CAPTCHA, MFA, a site error, or an inaccessible field, stop and report it. Do not guess or bypass it. "
        "Submit the completed application once. Then inspect the confirmation page and report the application ID or confirmation text. "
        "Do not claim success unless a confirmation is visible."
    )


async def apply(url: str, profile: dict, resume_path: Path, output_dir: Path, headless: bool = False, browser_data_dir: Path | None = None) -> dict:
    from browser_use import Agent, Browser

    output_dir.mkdir(parents=True, exist_ok=True)
    browser_options = {"headless": headless, "keep_alive": True}
    if browser_data_dir:
        browser_data_dir.mkdir(parents=True, exist_ok=True)
        for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            lock = browser_data_dir / name
            if lock.is_symlink():
                lock.unlink()
        browser_options["user_data_dir"] = browser_data_dir
    browser = Browser(**browser_options)
    agent = Agent(
        task=build_task(url, profile, resume_path),
        llm=make_llm(),
        browser=browser,
        flash_mode=os.getenv("LLM_PROVIDER", "ollama").lower() == "ollama",
        use_vision=(
            os.getenv("LLM_PROVIDER", "ollama").lower() != "ollama"
            or os.getenv("OLLAMA_USE_VISION", "false").lower() in {"1", "true", "yes"}
        ),
        available_file_paths=[str(resume_path.resolve())],
        save_conversation_path=output_dir / "conversation",
        max_failures=4,
        llm_timeout=240,
        step_timeout=300,
    )
    result = {"url": url, "started_at": datetime.now(timezone.utc).isoformat(), "status": "error"}
    try:
        history = await agent.run(max_steps=40)
        current_url = await browser.get_current_page_url()
        result.update({
            "final_url": current_url,
            "agent_done": history.is_done(),
            "agent_successful": history.is_successful(),
            "agent_result": history.final_result(),
            "errors": [str(error) for error in history.errors() if error],
            "steps": history.number_of_steps(),
        })
        if is_mock_url(url):
            expected = urlparse(url)
            actual = urlparse(current_url)
            confirmed = actual.hostname == expected.hostname and actual.port == expected.port and actual.path.startswith("/confirmation/")
            if confirmed:
                try:
                    with urlopen(current_url, timeout=5) as response:
                        confirmed = response.status == 200 and b"Application ID:" in response.read()
                except Exception:
                    confirmed = False
            result["application_id"] = actual.path.removeprefix("/confirmation/") if confirmed else None
        else:
            confirmed = bool(history.is_successful() and "confirm" in (history.final_result() or "").lower())
        result["status"] = "confirmed" if confirmed and history.is_successful() else "unconfirmed"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            await browser.take_screenshot(path=str(output_dir / "final.png"))
            result["screenshot"] = str(output_dir / "final.png")
        except Exception as exc:
            result["screenshot_error"] = str(exc)
        await browser.close()
        (output_dir / "result.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result


def run_application(url: str, profile_path: Path, resume_path: Path, output_dir: Path, authorized_url: str | None = None, headless: bool = False, browser_data_dir: Path | None = None) -> dict:
    if not is_mock_url(url) and authorized_url != url:
        raise ValueError("Real-site submission requires authorization for the exact URL")
    require_submission_authorization(url, authorized_url == url)
    profile = load_profile(profile_path, resume_path)
    return asyncio.run(apply(url, profile, resume_path, output_dir, headless=headless, browser_data_dir=browser_data_dir))


def main():
    parser = argparse.ArgumentParser(description="Apply to a job using Browser Use")
    parser.add_argument("--url", required=True)
    parser.add_argument("--profile", type=Path, default=Path("profile.json"))
    parser.add_argument("--resume", type=Path, default=Path("resume.pdf"))
    parser.add_argument("--authorize-submit", action="store_true", help="Explicitly authorize submission to a real site")
    args = parser.parse_args()
    load_dotenv()
    try:
        output_dir = Path("runs") / datetime.now().strftime("%Y%m%d-%H%M%S")
        result = run_application(args.url, args.profile, args.resume, output_dir, args.url if args.authorize_submit else None)
        print(json.dumps({"status": result["status"], "application_id": result.get("application_id"), "output_dir": str(output_dir), "error": result.get("error")}, indent=2))
        raise SystemExit(0 if result["status"] == "confirmed" else 1)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
