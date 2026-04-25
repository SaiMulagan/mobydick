from extract import extract_filters

cases = [
    ("18th century Russian literature", "bus/commute read", "challenging, I have prior experience"),
    ("Japanese magical realism",        "evening read",     "moderate"),
    ("popular science about astrophysics", "long project",  "easy"),
    ("ancient greek philosophy",        "weekend reads",    "challenging"),
]

for genre, time, diff in cases:
    print(f"\n--- {genre!r} | {time!r} | {diff!r} ---")
    f = extract_filters(genre, time, diff)
    print(f.model_dump_json(indent=2))