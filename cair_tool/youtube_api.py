import re
import time
from typing import Any, Dict, Iterable, List, Optional
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class YouTubeClient:
    def __init__(self, api_key: str):
        self.youtube = build("youtube", "v3", developerKey=api_key, cache_discovery=False)

    def _call(self, service, method, **kwargs) -> Dict[str, Any]:
        # Drop None-valued kwargs (e.g. pageToken=None) so the API isn't sent nulls.
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        for attempt in range(6):
            try:
                return getattr(service, method)(**kwargs).execute()
            except HttpError as exc:
                # googleapiclient HttpError exposes the HTTP status at exc.resp.status,
                # NOT exc.status_code. Retry transient 5xx with exponential backoff;
                # re-raise everything else (cli.py inspects exc.content for
                # commentsDisabled / quotaExceeded).
                status = getattr(getattr(exc, "resp", None), "status", None)
                try:
                    status = int(status) if status is not None else None
                except (TypeError, ValueError):
                    status = None
                if status is not None and 500 <= status < 600 and attempt < 5:
                    time.sleep(2 ** attempt)
                    continue
                raise
        raise RuntimeError("Unrecoverable YouTube API failure")

    def videos_list(self, video_ids: List[str]) -> Dict[str, Any]:
        if not video_ids:
            return {"items": []}
        return self._call(self.youtube.videos(), "list", part="statistics,snippet", id=",".join(video_ids))

    def search_list(self, query: str, max_results: int = 25, page_token: Optional[str] = None) -> Dict[str, Any]:
        return self._call(
            self.youtube.search(),
            "list",
            part="snippet",
            q=query,
            type="video",
            maxResults=max_results,
            pageToken=page_token,
        )

    def comment_threads(self, video_id: str, page_token: Optional[str], max_results: int = 100, order: str = "time") -> Dict[str, Any]:
        return self._call(
            self.youtube.commentThreads(),
            "list",
            part="snippet,replies",
            videoId=video_id,
            pageToken=page_token,
            maxResults=max_results,
            order=order,
            textFormat="plainText",
        )

    def comments_list(self, parent_id: str, page_token: Optional[str], max_results: int = 100) -> Dict[str, Any]:
        return self._call(
            self.youtube.comments(),
            "list",
            part="snippet",
            parentId=parent_id,
            pageToken=page_token,
            maxResults=max_results,
            textFormat="plainText",
        )


def normalize_video_id(url: str) -> Optional[str]:
    if not url:
        return None
    s = url.strip()
    # Bare 11-character video ID
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    # watch?v=, /shorts/, youtu.be/ — capture the 11-char id in any position
    match = re.search(r"(?:v=|/shorts/|youtu\.be/)([A-Za-z0-9_-]{11})", s)
    if match:
        return match.group(1)
    return None


def comment_permalink(video_id: str, comment_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}"
