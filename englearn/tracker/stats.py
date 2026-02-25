"""Statistics and progress reports."""
from datetime import datetime, timedelta
from englearn.db import models
from englearn.db.database import get_connection


def show_stats(period_days: int = 30):
    """Show comprehensive statistics."""
    conn = get_connection()
    try:
        # Overall entry stats
        total = conn.execute("SELECT COUNT(*) as c FROM log_entries").fetchone()['c']
        correct = conn.execute("SELECT COUNT(*) as c FROM log_entries WHERE status='correct'").fetchone()['c']
        incorrect = total - correct

        # Category breakdown
        cat_stats = models.get_category_stats()

        # Flashcard stats
        deck_stats = models.get_deck_stats()
        total_cards = sum(d['total'] for d in deck_stats)
        due_cards = sum(d['due'] for d in deck_stats)
        mastered_cards = sum(d['mastered'] for d in deck_stats)

        # Quiz stats
        quiz_total = conn.execute("SELECT COUNT(*) as c FROM quiz_results").fetchone()['c']
        quiz_correct = conn.execute("SELECT SUM(is_correct) as c FROM quiz_results").fetchone()['c'] or 0

        # Progress history
        progress = models.get_progress_history(period_days)

        # Streak calculation
        streak = _calculate_streak(progress)

    finally:
        conn.close()

    # Print report
    print(f"\n  {'═' * 55}")
    print(f"  English Learning Progress")
    print(f"  {'═' * 55}")
    print()
    print(f"  Log Statistics")
    print(f"  {'─' * 40}")
    print(f"  Total interactions:  {total}")
    print(f"  Correct:             {correct} ({correct * 100 // total if total else 0}%)")
    print(f"  Errors:              {incorrect} ({incorrect * 100 // total if total else 0}%)")
    print()

    # Error breakdown
    if cat_stats:
        print(f"  Error Breakdown")
        print(f"  {'─' * 40}")
        max_count = max(c['count'] for c in cat_stats) if cat_stats else 1
        for cs in cat_stats:
            bar_len = int(cs['count'] / max_count * 20)
            bar = '█' * bar_len + '░' * (20 - bar_len)
            pct = cs['count'] * 100 // incorrect if incorrect else 0
            name = _category_display_name(cs['category'])
            print(f"    {name:<22} {bar} {pct:>3}% ({cs['count']})")
        print()

    # Flashcard stats
    print(f"  Flashcard Progress")
    print(f"  {'─' * 40}")
    print(f"  Total cards:    {total_cards}")
    print(f"  Due today:      {due_cards}")
    print(f"  Mastered:       {mastered_cards}")
    if deck_stats:
        print()
        print(f"    {'Deck':<16} {'Total':>6} {'Due':>6} {'Mastered':>10}")
        print(f"    {'─' * 42}")
        for d in deck_stats:
            print(f"    {d['deck']:<16} {d['total']:>6} {d['due']:>6} {d['mastered']:>10}")
    print()

    # Quiz stats
    print(f"  Quiz Performance")
    print(f"  {'─' * 40}")
    print(f"  Questions answered: {quiz_total}")
    if quiz_total:
        print(f"  Correct:            {quiz_correct} ({quiz_correct * 100 // quiz_total}%)")
    print()

    # Streak
    print(f"  Current streak:     {streak} day(s)")
    print()

    # Weak areas
    weak = models.get_weak_categories()
    if weak:
        print(f"  Weakest Areas (need more practice)")
        print(f"  {'─' * 40}")
        for i, (cat, acc) in enumerate(weak, 1):
            name = _category_display_name(cat)
            print(f"    {i}. {name} (accuracy: {acc:.0%})")
        print()

    print(f"  {'═' * 55}\n")


def _calculate_streak(progress) -> int:
    """Calculate consecutive days with activity."""
    if not progress:
        return 0
    today = datetime.now().strftime("%Y-%m-%d")
    dates = {p['date'] for p in progress if p['cards_reviewed'] > 0 or p['quiz_taken'] > 0}
    streak = 0
    check_date = datetime.now()
    for _ in range(365):
        ds = check_date.strftime("%Y-%m-%d")
        if ds in dates:
            streak += 1
        else:
            break
        check_date -= timedelta(days=1)
    return streak


def _category_display_name(cat: str) -> str:
    names = {
        'chinese_mix': 'Chinese mixing',
        'spelling': 'Spelling/Typos',
        'article': 'Articles (a/the)',
        'preposition': 'Prepositions',
        'incomplete': 'Incomplete sent.',
        'capitalization': 'Capitalization',
        'tense': 'Tense errors',
        'word_choice': 'Word choice',
        'punctuation': 'Punctuation',
        'other': 'Other',
    }
    return names.get(cat, cat)
