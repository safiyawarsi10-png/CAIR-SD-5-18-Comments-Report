import argparse
import csv
import math
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from anthropic import Anthropic, RateLimitError

from cair_tool.classifier import classify_comment, escalation_flag_for_row
from cair_tool.config import load_config, load_rubric
from cair_tool.exporter import export_workbook
from cair_tool.store import (
    get_connection,
    initialize_store,
    upsert_video,
    save_comment_rows,
    get_unclassified_comments,
    get_comments_for_export,
    get_video_summary,
    mark_comments_for_classification,
)
from cair_tool.youtube_api import YouTubeClient, normalize_video_id, comment_permalink


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CAIR YouTube comment collection CLI")
    parser.add_argument("--config", default="config.yaml", help="Path to YAML configuration file")
    subparsers = parser.add_subparsers(dest="command", required=True)

    count = subparsers.add_parser("count", help="Fetch video metadata and estimate comment collection quota")
    count.add_argument("--video-map", help="CSV with video_url and stratification columns")
    count.add_argument("--search-query", help="Search query for YouTube videos")
    count.add_argument("--max-search-results", type=int, default=25, help="Maximum search results to return")

    collect = subparsers.add_parser("collect", help="Collect comments for mapped videos")
    collect.add_argument("--video-map", required=True, help="CSV with video_url and stratification columns")
    collect.add_argument("--fetch-replies", action="store_true", help="Fetch full reply trees via comments.list")
    collect.add_argument("--comment-order", choices=["time", "relevance"], help="Override comment order")

    classify = subparsers.add_parser("classify", help="Run Anthropic classification over unclassified comments")
    classify.add_argument("--delay", type=float, default=1.5, help="Seconds to wait between API calls (rate-limit pacing)")
    export = subparsers.add_parser("export", help="Export collected comments into .xlsx and CSV")
    return parser.parse_args()


def read_video_map(path: str) -> List[Dict[str, str]]:
    videos = []
    with Path(path).open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if not row.get("video_url"):
                continue
            videos.append({
                "video_url": row["video_url"].strip(),
                "outlet_tier": row.get("outlet_tier", "").strip(),
                "coverage_wave": row.get("coverage_wave", "").strip(),
                "format": row.get("format", "").strip(),
            })
    return videos


def chunked(iterable: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


def build_video_rows(videos: List[Dict[str, str]], client: YouTubeClient, config: dict, search_query: Optional[str] = None) -> List[Dict[str, object]]:
    if search_query:
        return search_videos(client, search_query, config.get("max_search_results", 25))
    ids = []
    for v in videos:
        vid = normalize_video_id(v["video_url"])
        if vid:
            ids.append(vid)
    rows = []
    for group in chunked(ids, 50):
        response = client.videos_list(group)
        for item in response.get("items", []):
            rows.append(item)
    return rows


def search_videos(client: YouTubeClient, query: str, max_results: int) -> List[Dict[str, object]]:
    results = []
    page_token = None
    fetched = 0
    while fetched < max_results:
        remaining = min(max_results - fetched, 25)
        response = client.search_list(query, max_results=remaining, page_token=page_token)
        for item in response.get("items", []):
            if item.get("id", {}).get("videoId"):
                results.append({"id": item["id"]["videoId"], "snippet": item["snippet"]})
        fetched += len(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return results


def format_count_table(items: List[Dict[str, object]]) -> str:
    lines = [
        "video_id | title | comments | estimated_units_to_collect | video_url",
        "--- | --- | --- | --- | ---",
    ]
    for item in sorted(items, key=lambda x: int(x.get("statistics", {}).get("commentCount", 0) or 0), reverse=True):
        comment_count = int(item.get("statistics", {}).get("commentCount", 0) or 0)
        units = math.ceil(comment_count / 100)
        lines.append(
            f"{item['id']} | {item.get('snippet', {}).get('title', '')[:60]} | {comment_count} | {units} | https://www.youtube.com/watch?v={item['id']}"
        )
    return "\n".join(lines)


def extract_error_reason(exc: Exception) -> Optional[str]:
    try:
        from googleapiclient.errors import HttpError

        if isinstance(exc, HttpError):
            content = exc.content.decode("utf-8", errors="ignore")
            if "commentsDisabled" in content:
                return "commentsDisabled"
            if "quotaExceeded" in content:
                return "quotaExceeded"
            if "dailyLimitExceeded" in content:
                return "quotaExceeded"
    except Exception:
        pass
    return None


def normalize_comment_thread(thread: Dict[str, object], video_id: str, video_title: str, video_url: str, video_published_at: str, video_view_count: int, video_comment_count: int, outlet_tier: str, coverage_wave: str, format_value: str, collected_at: str, collection_method: str, sample_method: str, include_inline_replies: bool = True) -> List[Dict[str, object]]:
    rows = []
    top = thread["snippet"]["topLevelComment"]
    snippet = top["snippet"]
    comment_id = top["id"]
    row = {
        "comment_id": comment_id,
        "comment_permalink": comment_permalink(video_id, comment_id),
        "comment_text": snippet.get("textDisplay", ""),
        "parent_comment_id": "",
        "thread_level": "top_level",
        "like_count": snippet.get("likeCount", 0),
        "reply_count": snippet.get("totalReplyCount", 0),
        "published_at": snippet.get("publishedAt"),
        "updated_at": snippet.get("updatedAt"),
        "author_display_name": snippet.get("authorDisplayName"),
        "author_channel_id": snippet.get("authorChannelId", {}).get("value"),
        "author_channel_url": snippet.get("authorChannelUrl"),
        "video_id": video_id,
        "video_title": video_title,
        "video_url": video_url,
        "channel_name": snippet.get("authorDisplayName"),
        "channel_id": snippet.get("authorChannelId", {}).get("value"),
        "video_published_at": video_published_at,
        "video_view_count": video_view_count,
        "video_comment_count": video_comment_count,
        "islamophobic": None,
        "islamophobia_category": None,
        "severity": None,
        "target": None,
        "triggering_span": None,
        "is_counterspeech": None,
        "overall_sentiment": None,
        "detected_language": None,
        "language_confidence": None,
        "english_translation": None,
        "model_confidence": None,
        "model_rationale": None,
        "model_version": None,
        "rubric_version": None,
        "human_reviewed": None,
        "reviewer_id": None,
        "review_date": None,
        "model_human_agreement": None,
        "final_label": None,
        "review_notes": None,
        "effective_label": None,
        "outlet_tier": outlet_tier,
        "coverage_wave": coverage_wave,
        "format": format_value,
        "collected_at": collected_at,
        "collection_method": collection_method,
        "sample_method": sample_method,
        "comment_live_at_collection": 1,
        "escalation_flag": 0,
    }
    rows.append(row)
    if include_inline_replies:
        for reply in thread.get("replies", {}).get("comments", []):
            rep_snippet = reply["snippet"]
            rep_id = reply["id"]
            rows.append(
                {
                    **row,
                    "comment_id": rep_id,
                    "comment_permalink": comment_permalink(video_id, rep_id),
                    "comment_text": rep_snippet.get("textDisplay", ""),
                    "parent_comment_id": comment_id,
                    "thread_level": "reply",
                    "like_count": rep_snippet.get("likeCount", 0),
                    "reply_count": 0,
                    "published_at": rep_snippet.get("publishedAt"),
                    "updated_at": rep_snippet.get("updatedAt"),
                    "author_display_name": rep_snippet.get("authorDisplayName"),
                    "author_channel_id": rep_snippet.get("authorChannelId", {}).get("value"),
                    "author_channel_url": rep_snippet.get("authorChannelUrl"),
                    "channel_name": rep_snippet.get("authorDisplayName"),
                    "channel_id": rep_snippet.get("authorChannelId", {}).get("value"),
                }
            )
    return rows


def collect_comments_for_video(client: YouTubeClient, conn, video_meta: dict, config: dict, fetch_replies: bool, order_override: Optional[str]) -> int:
    video_id = video_meta["video_id"]
    already = 0
    page_token = video_meta.get("next_page_token")
    collected_at = datetime.utcnow().isoformat() + "Z"
    order = order_override or config.get("comment_order", "time")
    while True:
        try:
            response = client.comment_threads(video_id=video_id, page_token=page_token, order=order)
        except Exception as exc:
            reason = extract_error_reason(exc)
            if reason == "commentsDisabled":
                upsert_video(conn, {**video_meta, "comments_disabled": 1, "next_page_token": None})
                print(f"Comments disabled for video {video_id}; skipping.")
                return already
            if reason == "quotaExceeded":
                print("Quota exceeded during collection; stopping. Resume later.")
                raise
            raise
        threads = response.get("items", [])
        if not threads:
            upsert_video(conn, {**video_meta, "next_page_token": None})
            return already
        comment_rows = []
        for thread in threads:
            comment_rows.extend(
                normalize_comment_thread(
                    thread,
                    video_id,
                    video_meta.get("video_title", ""),
                    video_meta.get("video_url", ""),
                    video_meta.get("video_published_at", ""),
                    video_meta.get("video_view_count", 0),
                    video_meta.get("video_comment_count", 0),
                    video_meta.get("outlet_tier", ""),
                    video_meta.get("coverage_wave", ""),
                    video_meta.get("format", ""),
                    collected_at,
                    config.get("collection_method", "YouTube Data API v3"),
                    config.get("sample_method", "hand_curated_url_list"),
                    include_inline_replies=not fetch_replies,
                )
            )
            if fetch_replies and thread["snippet"].get("totalReplyCount", 0) > 0:
                parent_id = thread["snippet"]["topLevelComment"]["id"]
                base_rows = normalize_comment_thread(
                    thread,
                    video_id,
                    video_meta.get("video_title", ""),
                    video_meta.get("video_url", ""),
                    video_meta.get("video_published_at", ""),
                    video_meta.get("video_view_count", 0),
                    video_meta.get("video_comment_count", 0),
                    video_meta.get("outlet_tier", ""),
                    video_meta.get("coverage_wave", ""),
                    video_meta.get("format", ""),
                    collected_at,
                    config.get("collection_method", "YouTube Data API v3"),
                    config.get("sample_method", "hand_curated_url_list"),
                    include_inline_replies=False,
                )
                base_row = base_rows[0]
                reply_token = None
                while True:
                    try:
                        reply_response = client.comments_list(parent_id=parent_id, page_token=reply_token)
                    except Exception as exc:
                        reason = extract_error_reason(exc)
                        if reason == "quotaExceeded":
                            print("Quota exceeded during reply fetch; stopping. Resume later.")
                            raise
                        raise
                    for reply in reply_response.get("items", []):
                        snippet = reply["snippet"]
                        row = dict(base_row)
                        row.update(
                            {
                                "comment_id": reply["id"],
                                "comment_permalink": comment_permalink(video_id, reply["id"]),
                                "comment_text": snippet.get("textDisplay", ""),
                                "parent_comment_id": parent_id,
                                "thread_level": "reply",
                                "like_count": snippet.get("likeCount", 0),
                                "reply_count": 0,
                                "published_at": snippet.get("publishedAt"),
                                "updated_at": snippet.get("updatedAt"),
                                "author_display_name": snippet.get("authorDisplayName"),
                                "author_channel_id": snippet.get("authorChannelId", {}).get("value"),
                                "author_channel_url": snippet.get("authorChannelUrl"),
                                "channel_name": snippet.get("authorDisplayName"),
                                "channel_id": snippet.get("authorChannelId", {}).get("value"),
                            }
                        )
                        comment_rows.append(row)
                    reply_token = reply_response.get("nextPageToken")
                    if not reply_token:
                        break
        save_comment_rows(conn, comment_rows)
        already += len(comment_rows)
        page_token = response.get("nextPageToken")
        upsert_video(conn, {**video_meta, "next_page_token": page_token})
        if not page_token:
            break
        if config.get("per_video_comment_cap", 0) and already >= config["per_video_comment_cap"]:
            print(f"Per-video comment cap reached for {video_id}.")
            break
    return already


def count_command(args: argparse.Namespace, config: dict) -> None:
    client = YouTubeClient(config["youtube_api_key"])
    if args.video_map:
        videos = read_video_map(args.video_map)
        ids = [normalize_video_id(v["video_url"]) for v in videos if normalize_video_id(v["video_url"])]
        if not ids:
            raise SystemExit("No valid YouTube video URLs found in the map.")
        items = []
        for group in chunked(ids, 50):
            response = client.videos_list(group)
            items.extend(response.get("items", []))
    elif args.search_query:
        items = search_videos(client, args.search_query, args.max_search_results)
        print("NOTE: search.list costs 100 quota units per request. Use hand-curated URLs when possible.")
    else:
        raise SystemExit("Provide --video-map or --search-query for count.")
    print(format_count_table(items))


def collect_command(args: argparse.Namespace, config: dict) -> None:
    client = YouTubeClient(config["youtube_api_key"])
    conn = get_connection(config["db_path"])
    initialize_store(conn)
    videos = read_video_map(args.video_map)
    video_meta_list = []
    for entry in videos:
        vid = normalize_video_id(entry["video_url"])
        if not vid:
            print(f"Skipping invalid video URL: {entry['video_url']}")
            continue
        response = client.videos_list([vid])
        item = response.get("items", [])
        if not item:
            print(f"Video not found: {vid}")
            continue
        item = item[0]
        statistics = item.get("statistics", {})
        snippet = item.get("snippet", {})
        video_meta = {
            "video_id": vid,
            "video_url": entry["video_url"],
            "outlet_tier": entry.get("outlet_tier", ""),
            "coverage_wave": entry.get("coverage_wave", ""),
            "format": entry.get("format", ""),
            "video_title": snippet.get("title", ""),
            "video_published_at": snippet.get("publishedAt", ""),
            "video_view_count": int(statistics.get("viewCount", 0) or 0),
            "video_comment_count": int(statistics.get("commentCount", 0) or 0),
            "next_page_token": None,
            "comments_disabled": 0,
            "collected_at": datetime.utcnow().isoformat() + "Z",
            "sample_method": config.get("sample_method", "hand_curated_url_list"),
        }
        upsert_video(conn, video_meta)
        video_meta_list.append(video_meta)
    for video_meta in video_meta_list:
        try:
            count = collect_comments_for_video(
                client,
                conn,
                video_meta,
                config,
                fetch_replies=args.fetch_replies or config.get("collect_all_replies", False),
                order_override=args.comment_order,
            )
            print(f"Collected {count} comments for video {video_meta['video_id']}")
        except Exception as exc:
            print(f"Stopped collection for {video_meta['video_id']}: {exc}")
            return


def classify_command(args: argparse.Namespace, config: dict) -> None:
    conn = get_connection(config["db_path"])
    initialize_store(conn)
    unclassified = get_unclassified_comments(conn)
    if not unclassified:
        print("No unclassified comments found.")
        return
    rubric = load_rubric(config["rubric_path"])
    client = Anthropic(api_key=config["anthropic_api_key"])
    delay = getattr(args, "delay", 1.5)
    total = len(unclassified)
    print(f"Classifying {total} comments (pacing {delay}s between calls)...", flush=True)
    done = 0
    for row in unclassified:
        comment_text = row["comment_text"] or ""
        # Retry forever on rate limits; the run is resumable so this is safe.
        while True:
            try:
                classification = classify_comment(client, config["model"], rubric, comment_text)
                break
            except RateLimitError:
                print("  rate limited — waiting 30s...", flush=True)
                time.sleep(30)
        escalation = escalation_flag_for_row(classification, comment_text)
        effective_label = row["final_label"] if row["final_label"] else classification["islamophobic"]
        classification.update(
            {
                "model_version": config["model"],
                "rubric_version": config["rubric_version"],
                "escalation_flag": 1 if escalation else 0,
                "effective_label": effective_label,
            }
        )
        # Save immediately so progress is banked and the run is resumable.
        mark_comments_for_classification(conn, [(row["comment_id"], classification)])
        done += 1
        print(f"  classified {done}/{total}  ({row['comment_id']})", flush=True)
        time.sleep(delay)
    print(f"Done. Classified {done} comments.", flush=True)


def export_command(args: argparse.Namespace, config: dict) -> None:
    conn = get_connection(config["db_path"])
    initialize_store(conn)
    rows = [dict(row) for row in get_comments_for_export(conn)]
    video_rows = [dict(row) for row in get_video_summary(conn)]
    if not rows:
        raise SystemExit("No comments available for export.")
    out_path = export_workbook(rows, video_rows, config)
    print(f"Exported workbook to {out_path}")


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    if args.command == "count":
        count_command(args, config)
    elif args.command == "collect":
        collect_command(args, config)
    elif args.command == "classify":
        classify_command(args, config)
    elif args.command == "export":
        export_command(args, config)


if __name__ == "__main__":
    main()
