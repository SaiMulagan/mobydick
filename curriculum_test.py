from extract import extract_filters
from candidates import fetch_candidates
from curriculum import generate_curriculum

cases = [
    ("18th century Russian literature", "bus/commute read", "challenging, I have prior experience"),
    ("Japanese magical realism",        "evening read",     "moderate"),
    ("popular science about astrophysics", "long project",  "easy"),
    ("ancient greek philosophy",        "weekend reads",    "challenging"),
]

for genre, time, diff in cases:
    print(f"\n=== {genre!r} ===")
    f = extract_filters(genre, time, diff)
    rows = fetch_candidates(f)
    pool = rows[:25]  # cost-cap: top 25 by match_score
    print(f"pool size: {len(pool)}")
    curriculum = generate_curriculum(genre, time, diff, pool)
    print(f"\nArc: {curriculum.overall_arc}\n")
    for p in curriculum.picks:
        print(f"  Week {p.week}: {p.title} — {p.author}")
        print(f"           {p.reason}\n")