# Moby Dicks — Claude Code Context

## What this project is
A reading curriculum generator. A user inputs a topic and a time budget,
and the app generates a personalized, ordered reading list with check-ins
after each book. The core differentiator is completion prediction — we
optimize for books a user will actually finish, not just books they might
like. This is something a one-shot LLM prompt cannot replicate.

## Team
Aatish, Brandt, Sai

## Important constraint
Do not suggest alternative tools, frameworks, or databases to what is
listed below. All stack decisions are final. Do not suggest Streamlit,
MongoDB, Flask, Next.js, or any frontend framework other than Reflex.

---

## Stack (final, do not change)
| Layer | Tool |
|---|---|
| Frontend + backend | Reflex (pure Python, no JavaScript) |
| Database | PostgreSQL on Google Cloud SQL |
| LLM | Vertex AI — Gemini Flash |
| Hosting | Google Cloud Run |
| Secrets | Google Secret Manager |
| AI output logging + memory | Google Cloud Logging |
| Raw data staging | Google Cloud Storage (GCS) |
| Scraping | BeautifulSoup + requests (not Selenium unless JS-rendered page confirmed) |
| Reddit data | PRAW (Python Reddit API Wrapper) |
| Offline batch (optional) | Cloud Scheduler + Cloud Run Job |

---

## Architecture overview
See ARCHITECTURE.md for full detail. Key rules:

- Scraping is OFFLINE ONLY. It never runs at request time.
- Raw scraped data lands in GCS first, then gets cleaned and loaded into PostgreSQL.
- At request time: Reflex queries PostgreSQL → builds Gemini prompt →
  calls Vertex AI → caches result → returns curriculum to user.
- Cloud Logging stores Gemini outputs and is used as conversational memory
  across sessions by prepending prior AI outputs as context in new prompts.
- Curricula are cached in PostgreSQL by (topic + profile_bucket) to
  minimize redundant Gemini calls and control cost.

---

## Database tables
- `users` — profile, reading history, momentum score
- `curricula` — generated reading plans, cached by topic + profile_bucket
- `survey_responses` — onboarding and check-in responses
- `progress` — per-book completion tracking, projected vs actual dates
- `ratings` — per-book user ratings after check-ins
- `books` — book metadata, complexity scores, readability metrics

---

## UI screens (Reflex)
1. **Onboarding survey** — topic, time budget, reading history, goal type
2. **Curriculum view** — ordered book list with predicted completion probability
3. **Check-in** — post-book rating and feedback, triggers curriculum reoptimization
4. **Progress dashboard** — momentum score, pace vs projection, complexity curve

---

## Phase plan
- **Phase 1 (now):** Rule-based filtering + Gemini prompting. No ML training.
- **Phase 2:** scikit-learn reranker trained on check-in and completion data.
- **Phase 3:** PySpark batch analytics if user data grows large enough.

---

## Budget
$150 GCP student credits. Strict cost controls:
- Smallest available Cloud SQL tier
- Cloud Run scales to zero (min-instances=0 for dev, consider min=1 for demo day)
- Gemini token usage capped per request with one retry max
- Aggressive caching by (topic + profile_bucket) in PostgreSQL
- One Cloud Run service only

---

## What NOT to do
- Do not run scraping at request time
- Do not add a vector store or embeddings layer (PostgreSQL + Gemini context window is sufficient)
- Do not use Streamlit, Flask, Django, or any framework other than Reflex
- Do not use MongoDB (our data is relational)
- Do not use OpenAI or any LLM other than Vertex AI Gemini Flash
- Do not add TensorFlow or PyTorch in Phase 1
- Do not use PySpark in Phase 1
