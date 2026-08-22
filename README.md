# CAIR YouTube Comment Collection & Classification Tool

A Python command-line tool for collecting public YouTube comments on news coverage of the May 18, 2026 shooting at the Islamic Center of San Diego, classifying them for Islamophobic content against a versioned rubric, and exporting a documented, reviewable dataset for CAIR's report.

The tool is built around one requirement: **every number in the final report has to survive a skeptical reader.** That shapes the design throughout — a written rubric that ships with the code, a rubric version stamped on every row, human-review columns built into the export, denominators next to every rate, and a methodology sheet stating the limits of what the data can support.

---

## What it does

Four stages, run as separate commands, with a SQLite database in between so any stage can stop and resume:

| Stage | Command | What happens |
| --- | --- | --- |
| 1. Scope | `count` | Reads video metadata and estimates how much API quota collection will cost — before you spend any. |
| 2. Collect | `collect` | Pulls comment threads (and optionally full reply trees) via the YouTube Data API into a local database. |
| 3. Classify | `classify` | Sends each unclassified comment to Claude with the rubric and stores the structured label. |
| 4. Export | `export` | Builds a multi-sheet `.xlsx` workbook plus a flat CSV. |

Collection and classification are both **resumable**. Comments are keyed by `comment_id` and inserted with `INSERT OR IGNORE`, so re-running `collect` never duplicates rows or clobbers labels you already have. `classify` writes each result to the database immediately, so an interrupted run picks up exactly where it stopped.

---

## What it is *not*

This tool measures **the YouTube comment conversation on this coverage**. It is not a representative sample of public opinion, of San Diego, or of any population. Comment sections are self-selected and skew toward strong feeling in both directions. Every rate in the export is reported with its denominator for this reason, and the workbook's `methodology` sheet carries the caveat in writing so it travels with the file.

---

## Requirements

- Python 3.9+
- A **YouTube Data API v3** key ([Google Cloud Console](https://console.cloud.google.com/apis/credentials))
- An **Anthropic API key** ([Anthropic Console](https://console.anthropic.com/settings/keys)) — needed only for `classify`

---

## Setup

```bash
# 1. Install dependencies (a virtual environment is recommended)
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt

# 2. Add your API keys
cp .env.example .env
# then open .env and fill in both keys

# 3. Build your video list
cp videos_map.example.csv videos_map.csv
# then add one row per video you want to collect
```

`.env` and `videos_map.csv` are both gitignored. Keep them that way.

### The video map

`videos_map.csv` is the hand-curated list of videos to collect from. One row per video:

```csv
video_url,outlet_tier,coverage_wave,format
https://www.youtube.com/watch?v=EXAMPLE,national,breaking_news,long_form
```

| Column | Purpose | Values the export expects |
| --- | --- | --- |
| `video_url` | Full URL, `youtu.be` short link, `/shorts/` link, or a bare 11-character video ID | — |
| `outlet_tier` | Who published it | `national`, `local_san_diego`, `independent_commentary` |
| `coverage_wave` | Which phase of coverage | `breaking_news`, `manifesto_radicalization`, `official_briefings`, `community_response` |
| `format` | Video length category | `short`, `long_form` |

The last three columns are your stratification variables — they're what lets the `rates` sheet break Islamophobia rates down by outlet type, coverage phase, and format. **The values must match the lists above exactly**, because the workbook's breakdown formulas count on those literal strings. A typo produces a silent zero, not an error.

---

## Usage

### 1. `count` — estimate before you spend

```bash
python3 cli.py count --video-map videos_map.csv
```

Prints a table of every video with its comment count and the estimated quota units collection will cost (one unit per 100 comments). Run this first: the YouTube API gives you roughly 10,000 quota units per day, and a few large videos can consume the entire budget.

You can also discover videos by search instead of supplying a map:

```bash
python3 cli.py count --search-query "islamic center san diego shooting" --max-search-results 25
```

Use this sparingly. **Each `search.list` request costs 100 quota units** — a single search can cost as much as collecting 10,000 comments. Curating URLs by hand is both cheaper and more defensible methodologically, since you can document why each video is in the sample.

### 2. `collect` — pull the comments

```bash
python3 cli.py collect --video-map videos_map.csv
```

Options:

| Flag | Effect |
| --- | --- |
| `--fetch-replies` | Fetch complete reply trees via `comments.list` instead of only the replies YouTube returns inline. More complete, more quota. |
| `--comment-order time\|relevance` | Override the ordering in `config.yaml`. `time` is the defensible default — `relevance` is a YouTube-defined ranking you would have to explain. |

Videos with comments disabled are marked and skipped. If you hit the daily quota, collection stops cleanly and reports where — re-run the same command tomorrow and it resumes from the stored page token.

### 3. `classify` — label against the rubric

```bash
python3 cli.py classify
```

Every comment not yet classified is sent to Claude along with the full text of `rubric/rubric_v0.2.md`. The model returns structured JSON, which is written straight to the database.

| Flag | Effect |
| --- | --- |
| `--delay 1.5` | Seconds between API calls. Raise it if you're being rate-limited often. |

Behavior worth knowing:

- **Rate limits retry indefinitely** — the run waits 30 seconds and tries again rather than dying partway through a long job.
- **Unparseable responses fail safe.** If the model returns something that isn't valid JSON, the row is labeled `not_sure` with the rationale `PARSE_ERROR — routed to human review`, rather than being dropped or guessed at.
- **Non-`yes` rows are normalized** — category reset to `none` and severity to `0`, so no stray category can inflate a count.
- **Human labels win.** If a row already has a `final_label` from human review, that value carries into `effective_label`; the model's label never overwrites it.

### 4. `export` — build the workbook

```bash
python3 cli.py export
```

Writes `output/comments_export_<timestamp>.xlsx` and a matching `.csv`.

---

## The exported workbook

Seven sheets:

**`comments`** — one row per comment, with columns grouped and color-coded by origin:

| Group | Colour | Contents |
| --- | --- | --- |
| A | yellow | Comment and video metadata straight from YouTube |
| B | green | Model classification: label, category, severity, target, triggering span, counterspeech, sentiment, language, confidence, rationale, model and rubric version |
| C | blue | Human review: reviewer ID, date, agreement, final label, notes |
| D | pink | Your stratification variables |
| E | orange | Provenance: when collected, by what method, sampling method, escalation flag |

The `effective_label` column is a live spreadsheet formula, not a stored value — it reads the human `final_label` where one exists and falls back to the model's label otherwise. Type a correction into `final_label` and every rate in the workbook updates.

**`by_video`** — per-video counts and Islamophobia rate, as formulas over the `comments` sheet.

**`rates`** — the headline breakdowns: rate by `outlet_tier`, by `coverage_wave`, by `format`, plus an overall row. Each shows `K_yes`, `N_total`, and the rate, so no percentage ever appears without its denominator.

**`unique_accounts`** — distinct commenter count and the ten most frequent accounts. A handful of accounts producing a large share of the comments can indicate coordinated rather than organic activity, and is worth knowing before publishing.

**`validation`** — how many rows a human actually reviewed and how often the human agreed with the model. **This is the sheet that decides whether the dataset is defensible.** A low `reviewed_count` means the agreement rate is indicative only, and the sheet says so.

**`escalations`** — every comment flagged `threat_of_violence`, with permalinks. The model flags *all* threats and does not judge credibility; a human decides what is specific and credible and whether to report it to YouTube or the FBI. **The tool never reports anything automatically.**

**`methodology`** — comment and video counts, date range, collection and sampling method, model version, rubric version, quota ceiling, and the scope caveat, so the file documents itself if it circulates without this README.

---

## The rubric

`rubric/rubric_v0.2.md` is the methodology document, not a code comment. It defines the labels, the ideas-vs-people line at the center of the whole exercise, five categories with explicit include/exclude lists, severity, target, counterspeech, sentiment, and the edge cases (sarcasm, quotation, reclaimed speech, non-English text).

Two things to keep in mind when working with it:

1. **Precision over recall is deliberate.** When the model is torn between `yes` and `not_sure`, the rubric instructs it to choose `not_sure`. For a policy dataset, one indefensible "yes" lets a critic dismiss everything; a miss costs less.
2. **Version it when you change it.** Every classified row is stamped with `rubric_version` from `config.yaml`. If you edit the rubric, bump that value *and* rename the file, and keep the three in sync — the document's own heading, its filename, and `rubric_version`. If they drift apart, rows carry a version label that doesn't describe the definitions they were actually judged under, and the audit trail is worth nothing.

Rows classified before a version bump keep the old stamp, which is correct — they *were* labeled under the old definitions. If a change is substantive enough that the old labels shouldn't be mixed with the new ones, clear `classified` on those rows and re-run `classify` rather than relabeling them by hand.

The rubric still carries open items for CAIR sign-off before it can be promoted to v1.0.

---

## Configuration

`config.yaml`:

| Key | Default | Meaning |
| --- | --- | --- |
| `youtube_api_key_env` | `YOUTUBE_API_KEY` | Name of the env var holding the YouTube key |
| `anthropic_api_key_env` | `ANTHROPIC_API_KEY` | Name of the env var holding the Anthropic key |
| `db_path` | `data/comments.db` | SQLite database location |
| `rubric_path` | `rubric/rubric_v0.2.md` | Rubric sent to the classifier |
| `model` | `claude-haiku-4-5-20251001` | Classifier model |
| `rubric_version` | `v0.2` | Stamped on every classified row |
| `per_video_comment_cap` | `0` | Max comments per video; `0` means no cap |
| `collect_all_replies` | `false` | Fetch full reply trees by default |
| `comment_order` | `time` | `time` or `relevance` |
| `daily_quota_limit` | `9500` | Quota ceiling recorded in the methodology sheet |
| `output_dir` | `output` | Where exports are written |
| `sample_method` | `hand_curated_url_list` | Recorded on every row as provenance |

Secrets are never stored here — `config.yaml` only names the environment variables to read.

---

## Handling the data responsibly

- **Never commit `.env`.** It is gitignored; keep it that way, and rotate any key that reaches a commit.
- **The database and exports are not in this repository by design.** They contain real comment text, display names, and channel IDs of identifiable people. `data/`, `output/`, and `videos_map.csv` are all gitignored. Share exports deliberately, not by pushing them.
- **Threats need a human.** The `escalations` sheet is a triage queue, not a report. A person reviews each flagged comment and decides on reporting (FBI: 1-800-CALL-FBI).
- **Review before publishing.** The `validation` sheet exists so you know what your agreement rate actually rests on. Review enough rows — starting with every `yes` and `not_sure` — that the number means something.

---

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `Missing YouTube API key` | `.env` is missing, empty, or in a different directory. Run commands from the repository root. |
| `Quota exceeded during collection` | Daily YouTube quota is spent. Re-run tomorrow; it resumes from where it stopped. |
| `Comments disabled for video X` | Expected — the video is marked and skipped. |
| `No comments available for export` | The database is empty. Run `collect` first, and confirm `db_path` matches. |
| Many `PARSE_ERROR` rationales | The model is returning non-JSON. Check that `model` in `config.yaml` is a valid, current model ID. |
| Counts in `rates` are zero | A stratification value in `videos_map.csv` doesn't exactly match what the sheet counts — check spelling against the table above. |
| Rate limited constantly during `classify` | Raise `--delay`. |

---

## Project layout

```
.
├── cli.py                    # Command-line entry point; all four commands
├── cair_tool/
│   ├── config.py             # Loads config.yaml, resolves keys from .env
│   ├── youtube_api.py        # YouTube Data API client, retries, URL parsing
│   ├── classifier.py         # Anthropic call, strict-JSON parsing, escalation
│   ├── store.py              # SQLite schema and resumable read/write
│   └── exporter.py           # Multi-sheet .xlsx and flat CSV export
├── rubric/
│   └── rubric_v0.2.md        # Versioned classification methodology
├── config.yaml               # Non-secret settings
├── videos_map.example.csv    # Template for your video list
├── .env.example              # Template for your API keys
└── requirements.txt
```
