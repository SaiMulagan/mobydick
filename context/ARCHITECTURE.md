# Architecture — Moby Dicks

## End-to-end data flow

```
[Offline scraping] → GCS (raw) → PostgreSQL (structured)
                                        ↓
[User] → Reflex UI → Gemini prompt builder → Vertex AI (Gemini Flash)
                                        ↓
                              PostgreSQL (cache + store result)
                                        ↓
                              Reflex UI (curriculum returned to user)
```

---

## Layer 1: Offline data pipeline (runs once, or on schedule)

### Data sources
| Source | Method | What we extract |
|---|---|---|
| Open Syllabus Project | Dataset download | Book co-assignment, pedagogical ordering |
| Reddit (r/books, r/suggestmeabook, r/literature) | PRAW API | Sequencing recommendations, "where to start" threads |
| Wikipedia | Link graph crawl (requests + BS4) | Literary influence relationships between books |
| Project Gutenberg | Download count API | Proxy for real-world completion/read rate |

### Why not Goodreads
Goodreads actively blocks scrapers and has no public API. The UCSD
Goodreads dataset on Kaggle is an option for bootstrapping but creates
a hard dependency on a private company's continued data availability.
We use open and API-accessible sources instead.

### Pipeline steps
1. Run scraping scripts locally or via Cloud Run Job
2. Raw output (JSON/CSV) written to GCS bucket as staging
3. Separate cleaning script reads from GCS, transforms, loads into PostgreSQL
4. Raw GCS files preserved for reprocessing without re-scraping

### Scraping tools
- `requests` + BeautifulSoup for static HTML pages
- PRAW for Reddit (official API, no scraping needed)
- Wikipedia API for page content and link relationships
- Selenium only if a specific page is confirmed JavaScript-rendered

---

## Layer 2: Storage — Cloud SQL (PostgreSQL)

### Schema summary
```sql
users               -- id, profile, reading_history, momentum_score
books               -- id, title, author, page_count, readability_score,
                   --    vocab_rarity, genre, source, flesch_kincaid
curricula           -- id, user_id, topic, profile_bucket, book_order,
                   --    completion_probability, cached_at
survey_responses    -- id, user_id, question, response, created_at
progress            -- id, user_id, book_id, status, projected_date,
                   --    actual_date, pace_delta
ratings             -- id, user_id, book_id, rating, difficulty_felt,
                   --    abandoned (bool), created_at
```

### Caching strategy
Curricula are cached by `(topic, profile_bucket)`. Profile buckets are
derived from user momentum score and reading complexity history — users
with similar profiles share cached curricula. This is the primary Gemini
cost control mechanism.

---

## Layer 3: Application — Reflex on Cloud Run

### Reflex app responsibilities
- Serve all UI screens (survey, curriculum, check-in, dashboard)
- Handle all database reads and writes
- Build and fire Gemini prompts
- Pull Cloud Logging history for session memory
- Cache curriculum results back to PostgreSQL

### Request-time flow (curriculum generation)
1. User submits survey
2. Reflex queries PostgreSQL: candidate books matching topic + time budget
3. Reflex queries Cloud Logging: prior AI outputs for this user (session memory)
4. Prompt assembled: candidate books + user survey + prior context
5. Vertex AI (Gemini Flash) called — token cap enforced, one retry max
6. Response parsed, completion probability computed
7. Result written to `curricula` table (cached)
8. Gemini output written to Cloud Logging (for future memory)
9. Curriculum displayed to user

### Cloud Run configuration
- Single service (Reflex app)
- Scale to zero for dev/staging
- Min instances = 1 on demo day to avoid cold start
- Secrets injected from Secret Manager via environment variables at startup

---

## Layer 4: LLM — Vertex AI (Gemini Flash)

### Why Gemini Flash
- ~$0.075 per million input tokens (~25x cheaper than GPT-4o)
- Co-located with Cloud Run on GCP — auth via IAM, no API key management
- Internal network call, lower latency than cross-provider

### Prompt structure
```
SYSTEM: You are a reading curriculum expert. Generate a structured
        reading order based on the candidate books and user profile below.
        Return JSON only. Schema: [{title, author, reason, week}]

CONTEXT (from Cloud Logging — prior sessions):
  [prior Gemini outputs for this user, summarized if long]

USER PROFILE:
  Topic: {topic}
  Time budget: {weeks} weeks, {hours_per_week} hours/week
  Momentum score: {score}
  Complexity level: {level}
  Already read: {completed_books}

CANDIDATE BOOKS (from PostgreSQL):
  [{title, author, page_count, readability_score, sequencing_signals}]
```

### Memory management
Cloud Logging stores raw Gemini outputs. On each new request, recent
outputs are fetched and prepended as context. If history is long, a
lightweight Gemini call first summarizes older entries into a rolling
summary stored in PostgreSQL — this prevents context window bloat.

---

## Layer 5: Supporting GCP infrastructure

| Service | Role |
|---|---|
| Secret Manager | DB credentials, Gemini API key |
| Cloud Logging | AI output storage, error traces, app logs |
| Cloud Scheduler | Optional: triggers nightly data refresh |
| Cloud Run Job | Optional: runs batch recompute of stale curricula |
| Cloud Storage | Raw scrape staging, optional export storage |

---

## Complexity signals (for ordering books)
Books in the database are scored on:
- **Flesch-Kincaid readability** — sentence and word complexity
- **Vocabulary rarity** — proportion of uncommon words
- **Page count** — proxy for time and attention commitment
- **Sequencing signals** — Reddit thread co-mentions, syllabus week order,
  Wikipedia influence links
- **Completion proxy** — Project Gutenberg download count for public domain books

These signals combine to produce a "reading weight" per book, enabling
curricula that progressively increase difficulty — a reading version of
progressive overload in fitness training.
