# Decisions — Moby Dicks

All major decisions made during planning. Reference this before suggesting
changes to the stack or product direction.

---

## Stack decisions

### Reflex over Next.js / React
The team does not want to write JavaScript. Reflex compiles to React under
the hood but is authored entirely in Python — the same language as the
rest of the stack. This means one language across the entire project,
one deployment, one server to reason about. FastAPI was also dropped
because Reflex handles its own backend state, making a separate API
server redundant.

### PostgreSQL over MongoDB
Our data is relational. Users reference curricula, curricula reference
books, progress references both users and books, ratings reference users
and books. A document store would fight this structure. Cloud SQL
PostgreSQL is the right tool. MongoDB is explicitly not used even though
team members have experience with it.

### Gemini Flash over GPT-4o or Claude
Pricing is a hard constraint ($150 GCP credits). Gemini Flash costs ~$0.075
per million input tokens — approximately 25x cheaper than GPT-4o at the
same scale. Co-location with Cloud Run on GCP also simplifies auth (IAM
instead of API keys) and reduces network latency.

### No vector store
We considered pgvector and Pinecone for embeddings-based retrieval.
Decision: not needed. Gemini's context window is large enough to hold
a relevant subset of candidate books pulled directly from PostgreSQL with
a structured SQL query. Removing the vector store eliminates a dependency
and a cost surface.

### Cloud Logging for AI memory (not a custom memory table)
Rather than designing a separate conversation history schema, Gemini
outputs are written to Cloud Logging after each generation. On subsequent
requests, recent logs are fetched and prepended as context. This gives
Gemini session continuity without additional database schema complexity.
For users with long history, a rolling summary is stored in PostgreSQL
to prevent context window bloat.

### GCS as scrape staging layer
Raw scraped data lands in Google Cloud Storage before touching PostgreSQL.
This means the raw data can be reprocessed without re-scraping, and a
scraping failure cannot corrupt the live database. GCS is the separation
point between the offline data pipeline and the live application.

### No Goodreads dependency
Goodreads actively blocks scrapers and has no public API. Building on
Goodreads data creates a fragile dependency on a private company's
continued tolerance. We use open and API-accessible sources: Open Syllabus
Project, Reddit via PRAW, Wikipedia link graph, Project Gutenberg.

### requests + BeautifulSoup over Selenium
Selenium is compute-heavy (headless browser). Most of our target pages
(university syllabi, Wikipedia) render server-side and don't need a browser.
Selenium is only used if a specific page is confirmed to require JavaScript
rendering. PRAW replaces scraping for Reddit entirely.

---

## Product decisions

### Completion over preference
The app optimizes for books a user will actually finish, not books they
might like. These are different problems. Finish rate is the primary metric,
not rating. This is the core differentiator from asking an LLM for a
reading list — no LLM has behavioral completion data for real users.

### Offline scraping only
Scraping never runs at request time. All book data is pre-loaded into
PostgreSQL before the app serves any user. This separates the data
pipeline complexity from the application complexity and ensures scraping
failures cannot affect the live user experience.

### Caching by (topic + profile_bucket)
Generating a curriculum for every user independently is expensive. Users
with similar profiles reading the same topic get the same cached curriculum.
Profile buckets are derived from momentum score and complexity history.
This is the primary Gemini cost control mechanism.

### Prompt engineering over custom models (Phase 1)
No ML training in Phase 1. All recommendation logic lives in prompt
construction — candidate book selection from PostgreSQL, user profile,
sequencing signals, and session memory are assembled into a structured
prompt and Gemini does the ordering. Phase 2 adds a scikit-learn reranker
trained on check-in data if there is enough of it.

### One-prompt UX as core value proposition
A user getting a reading curriculum from ChatGPT would need 8-10 back-and-forth
exchanges to convey: reading level, time available, genre preferences, books
already read, books abandoned and why, goal type, length preference,
fiction vs nonfiction preference. Our survey captures all of this in one
structured form and fires a single optimized prompt. The user does one
thing; the app does the prompt engineering invisibly.

### Social accountability (planned, not Phase 1)
Two users can commit to a shared curriculum and track each other's progress.
Completion rates on shared plans are significantly higher than solo ones.
This is a structural advantage over LLMs — it requires accounts, shared
state, and a social graph that a chat interface cannot provide.

---

## Things explicitly ruled out

| What | Why |
|---|---|
| Streamlit | Banned by the course instructor |
| Flask / Django | Redundant given Reflex handles backend |
| MongoDB | Data is relational |
| OpenAI GPT-4o | 25x more expensive than Gemini Flash |
| Pinecone / pgvector | Not needed; Gemini context window sufficient |
| TensorFlow / PyTorch | Phase 3 only if data justifies it |
| PySpark | Phase 3 only if data grows large enough |
| Selenium | Only for confirmed JS-rendered pages |
| Goodreads scraping | Actively blocked, no public API |
| Request-time scraping | Separates pipeline from app; scraping failures must not affect users |
