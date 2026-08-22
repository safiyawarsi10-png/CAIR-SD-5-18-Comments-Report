import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

# Comment columns persisted in the DB (matches the row dicts built in cli.py
# and the HEADER_ROW the exporter reads).
COMMENT_COLUMNS = [
    "comment_id", "comment_permalink", "comment_text", "parent_comment_id",
    "thread_level", "like_count", "reply_count", "published_at", "updated_at",
    "author_display_name", "author_channel_id", "author_channel_url",
    "video_id", "video_title", "video_url", "channel_name", "channel_id",
    "video_published_at", "video_view_count", "video_comment_count",
    "islamophobic", "islamophobia_category", "severity", "target",
    "triggering_span", "is_counterspeech", "overall_sentiment",
    "detected_language", "language_confidence", "english_translation",
    "model_confidence", "model_rationale", "model_version", "rubric_version",
    "human_reviewed", "reviewer_id", "review_date", "model_human_agreement",
    "final_label", "review_notes", "effective_label",
    "outlet_tier", "coverage_wave", "format",
    "collected_at", "collection_method", "sample_method",
    "comment_live_at_collection", "escalation_flag",
]

VIDEO_COLUMNS = [
    "video_id", "video_url", "video_title", "video_published_at",
    "video_view_count", "video_comment_count", "outlet_tier", "coverage_wave",
    "format", "next_page_token", "comments_disabled", "collected_at", "sample_method",
]

# Column SQL affinities. Numeric/flag columns MUST be INTEGER/REAL, not TEXT —
# otherwise SQLite stores 1 as the string "1" and the exporter's COUNTIFS(...,1)
# (numeric criterion) won't match, silently zeroing the counts.
INTEGER_COLUMNS = {
    "like_count", "reply_count", "video_view_count", "video_comment_count",
    "severity", "is_counterspeech", "human_reviewed", "model_human_agreement",
    "comment_live_at_collection", "escalation_flag",
}
REAL_COLUMNS = {"language_confidence", "model_confidence"}


def _sql_type(col: str) -> str:
    if col in INTEGER_COLUMNS:
        return "INTEGER"
    if col in REAL_COLUMNS:
        return "REAL"
    return "TEXT"


# Columns updated when a comment is classified.
CLASSIFICATION_COLUMNS = [
    "islamophobic", "islamophobia_category", "severity", "target",
    "triggering_span", "is_counterspeech", "overall_sentiment",
    "detected_language", "language_confidence", "english_translation",
    "model_confidence", "model_rationale", "model_version", "rubric_version",
    "escalation_flag", "effective_label",
]


def _coerce(value):
    """SQLite has no bool type; store booleans as 1/0 so the exporter's
    COUNTIFS(..., 1) matching works. Leave everything else as-is."""
    if isinstance(value, bool):
        return 1 if value else 0
    return value


def get_connection(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_store(conn: sqlite3.Connection) -> None:
    comment_defs = ",\n".join(f"{col} {_sql_type(col)}" for col in COMMENT_COLUMNS)
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS comments (
            {comment_defs},
            classified INTEGER DEFAULT 0,
            PRIMARY KEY (comment_id)
        )"""
    )
    video_defs = ",\n".join(f"{col} TEXT" for col in VIDEO_COLUMNS)
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS videos (
            {video_defs},
            PRIMARY KEY (video_id)
        )"""
    )
    conn.commit()


def upsert_video(conn: sqlite3.Connection, video_meta: Dict[str, object]) -> None:
    cols = VIDEO_COLUMNS
    placeholders = ",".join("?" for _ in cols)
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "video_id")
    values = [_coerce(video_meta.get(c)) for c in cols]
    conn.execute(
        f"""INSERT INTO videos ({','.join(cols)}) VALUES ({placeholders})
            ON CONFLICT(video_id) DO UPDATE SET {updates}""",
        values,
    )
    conn.commit()


def save_comment_rows(conn: sqlite3.Connection, rows: List[Dict[str, object]]) -> None:
    if not rows:
        return
    cols = COMMENT_COLUMNS
    placeholders = ",".join("?" for _ in cols)
    # INSERT OR IGNORE: idempotent on comment_id; never clobbers an already-classified row.
    sql = f"INSERT OR IGNORE INTO comments ({','.join(cols)}) VALUES ({placeholders})"
    data = [[_coerce(row.get(c)) for c in cols] for row in rows]
    conn.executemany(sql, data)
    conn.commit()


def get_unclassified_comments(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    cur = conn.execute("SELECT * FROM comments WHERE classified = 0 OR classified IS NULL")
    return cur.fetchall()


def mark_comments_for_classification(
    conn: sqlite3.Connection, results: Iterable[Tuple[str, Dict[str, object]]]
) -> None:
    set_clause = ",".join(f"{c}=?" for c in CLASSIFICATION_COLUMNS) + ", classified=1"
    sql = f"UPDATE comments SET {set_clause} WHERE comment_id=?"
    payload = []
    for comment_id, classification in results:
        values = [_coerce(classification.get(c)) for c in CLASSIFICATION_COLUMNS]
        values.append(comment_id)
        payload.append(values)
    conn.executemany(sql, payload)
    conn.commit()


def get_comments_for_export(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute("SELECT * FROM comments").fetchall()


def get_video_summary(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    cols = ["video_id", "video_title", "video_url", "outlet_tier",
            "coverage_wave", "format", "video_view_count", "video_comment_count"]
    return conn.execute(f"SELECT {','.join(cols)} FROM videos").fetchall()
