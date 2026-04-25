import argparse
from pipeline import generate_for_survey


def main():
    p = argparse.ArgumentParser(description="Moby Dicks curriculum generator")
    p.add_argument("--genre",      required=True, help="e.g. 'Japanese magical realism'")
    p.add_argument("--time",       required=True, help="e.g. 'evening read'")
    p.add_argument("--difficulty", required=True, help="e.g. 'challenging'")
    args = p.parse_args()

    curriculum = generate_for_survey(args.genre, args.time, args.difficulty)

    print(f"\n=== Reading curriculum ===\n")
    print(f"{curriculum.overall_arc}\n")
    for pick in curriculum.picks:
        print(f"  Week {pick.week}: {pick.title} — {pick.author}")
        print(f"           {pick.reason}\n")


if __name__ == "__main__":
    main()