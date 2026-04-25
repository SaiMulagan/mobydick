# Product — Moby Dicks

## One-line pitch
"We don't recommend books you'll like. We recommend books you'll actually finish."

## Problem
Finding books to read is not hard. Finishing them is. The overwhelming
majority of "want to read" lists are never touched. Reddit is full of
people asking why they can't finish books anymore. The real problem is
not curation — it's follow-through.

Existing solutions (LLMs, Goodreads recommendations, "best of" lists)
optimize for preference. None of them optimize for completion.

---

## Core differentiators from asking an LLM the same question

Each item below describes something structurally impossible in a chat interface.

### 1. Behavioral completion data
The app tracks which books users actually finish, where they abandon books,
and which sequences lead to completion vs dropout. An LLM has no access
to this behavioral history. It can suggest books you might like — it cannot
predict whether you will finish them based on your actual past behavior.

### 2. Persistent memory across sessions
A standalone LLM has no memory of what you've already read, what you rated
highly, or where you dropped off. The app accumulates reading history per
user and uses it in every new curriculum. After three curricula, the
recommendations are personalized in a way no single conversation can replicate.

### 3. The check-in loop
A one-shot LLM response is static. The app asks "how did this book feel?"
after each one and reoptimizes the rest of the curriculum based on the
answer. If a user rates a book too dense, books 4-8 adjust automatically.
No conversation thread maintains this kind of structured feedback loop
without the user manually managing it — and nobody does.

### 4. Time-awareness as a hard constraint
When a user says "3 hours a week for 6 weeks," the app computes against
actual page counts and average reading speeds from book metadata. The
constraint is mathematically enforced. An LLM approximates this — it has
no access to actual reading time data per book.

### 5. One prompt vs twenty
A user prompting ChatGPT for a quality reading curriculum would need to
convey: reading level, time budget, genre preferences, already-read books,
abandoned books and why, goal type, length preference, fiction/nonfiction
mix. That's 8-10 exchanges minimum. Our onboarding survey captures all of
it in one structured form. The user does one thing; the app does the
prompt engineering invisibly.

### 6. Progressive difficulty (reading progressive overload)
Books in the database are scored on measurable complexity axes:
Flesch-Kincaid readability, vocabulary rarity, page count, structural
complexity. Curricula can be set to increase difficulty deliberately across
these dimensions — a reading training program, not just a list. An LLM
cannot compute these metrics; it can only approximate them from training data.

### 7. Social accountability (Phase 2)
Two users commit to a shared curriculum and track each other's progress.
Completion rates on shared plans are significantly higher than solo ones.
A chat interface is by definition a solo interaction — it cannot provide
a social layer, shared state, or accountability partner.

---

## User flow

```
1. Onboarding survey
   → Topic, time budget (hours/week × weeks), reading history seed,
     goal type (entertainment / education / skill), length preference

2. Curriculum generated
   → Ordered reading list with predicted completion probability per book
   → Complexity progression shown
   → Estimated read time per book

3. Check-in after each book
   → Single-question rating: too easy / just right / too dense / abandoned
   → Optional free text
   → Remaining curriculum reoptimizes based on response

4. Progress dashboard
   → Momentum score (behavioral, not self-reported)
   → Pace vs projection
   → Complexity curve over time
   → Finish rate by genre / length / era
```

---

## Metrics (what success looks like)
- **Primary:** Curriculum completion rate (% of curricula where user finishes all books)
- **Secondary:** Check-in engagement rate (% of completions with a check-in submitted)
- **Secondary:** Return rate (% of users who generate a second curriculum)
- **Cost:** Gemini spend per curriculum generation (target: <$0.01 per generation)

---

## Roadmap

### Phase 1 — MVP (now)
- Onboarding survey
- Gemini-generated curriculum with PostgreSQL candidate pool
- Check-in after each book
- Basic progress dashboard
- GCS + PostgreSQL data pipeline from open sources
- Cloud Run deployment with caching

### Phase 2 — Behavioral model
- scikit-learn reranker trained on check-in and completion data
- Reading personality diagnostic (completion rate by genre/length/complexity)
- Momentum score displayed to user
- Social curriculum sharing (two-user accountability)

### Phase 3 — Scale (if data warrants)
- PySpark batch analytics on completion patterns
- Cross-genre bridge recommendations from behavioral data
- Context-aware daily recommendation ("what to read right now")
- "Reading debt" resolver — import and structure backlog
