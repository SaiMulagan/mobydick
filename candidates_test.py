from extract import extract_filters
from candidates import fetch_candidates

cases = [
    ("18th century Russian literature", "bus/commute read", "challenging, I have prior experience"),
    ("Japanese magical realism",        "evening read",     "moderate"),
    ("popular science about astrophysics", "long project",  "easy"),
    ("ancient greek philosophy",        "weekend reads",    "challenging"),
]

for genre, time, diff in cases:
    print(f"\n=== {genre!r} ===")
    filters = extract_filters(genre, time, diff)
    rows = fetch_candidates(filters)
    print(f"{len(rows)} candidates")
    for r in rows[:5]:
        shelves = list(r.top_shelves)[:3]
        print(f"  [{r.publication_year}] {r.title} — {r.num_pages}p, "
              f"{r.ratings_count:,} ratings, shelves: {shelves}")