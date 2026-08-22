import os
from pathlib import Path
from typing import Dict

import yaml

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def load_config(path: str = "config.yaml") -> Dict[str, object]:
    config_path = Path(path)
    if not config_path.exists():
        raise SystemExit(f"Config file not found: {path}")
    with config_path.open("r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}

    # Resolve API keys from the environment variables named in the config.
    # The actual secrets live in .env, never in this file.
    yt_env = config.get("youtube_api_key_env", "YOUTUBE_API_KEY")
    an_env = config.get("anthropic_api_key_env", "ANTHROPIC_API_KEY")
    config["youtube_api_key"] = os.environ.get(yt_env, "")
    config["anthropic_api_key"] = os.environ.get(an_env, "")

    if not config["youtube_api_key"]:
        raise SystemExit(
            f"Missing YouTube API key. Set {yt_env} in your .env file "
            f"(e.g. {yt_env}=AIza...)."
        )
    # Anthropic key is only needed for `classify`; warn lazily rather than hard-fail here,
    # but still surface it clearly if absent.
    # (classify_command will fail clearly if it's empty.)

    # Normalize quota key: accept either name, expose both.
    quota = config.get("daily_quota_ceiling", config.get("daily_quota_limit", 9500))
    config["daily_quota_ceiling"] = quota
    config["daily_quota_limit"] = quota

    # Defaults the rest of the code may read with [] rather than .get().
    config.setdefault("model", "claude-sonnet-4-6")
    config.setdefault("rubric_version", "v0.1")
    config.setdefault("rubric_path", "rubric/rubric_v0.1.md")
    config.setdefault("db_path", "data/comments.db")
    config.setdefault("output_dir", "output")
    config.setdefault("comment_order", "time")
    config.setdefault("per_video_comment_cap", 0)
    config.setdefault("collect_all_replies", False)
    config.setdefault("collection_method", "YouTube Data API v3")
    config.setdefault("sample_method", "hand_curated_url_list")
    config.setdefault("max_search_results", 25)
    return config


def load_rubric(path: str) -> str:
    rubric_path = Path(path)
    if not rubric_path.exists():
        raise SystemExit(f"Rubric file not found: {path}")
    return rubric_path.read_text(encoding="utf-8")
