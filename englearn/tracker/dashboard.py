"""ASCII dashboard for quick overview."""
from datetime import datetime
from englearn.db import models
from englearn.db.database import get_connection


def show_dashboard():
    """Show a compact dashboard with key metrics."""
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) as c FROM log_entries").fetchone()['c']
        correct = conn.execute("SELECT COUNT(*) as c FROM log_entries WHERE status='correct'").fetchone()['c']

        deck_stats = models.get_deck_stats()
        total_cards = sum(d['total'] for d in deck_stats)
        due_cards = sum(d['due'] for d in deck_stats)
        mastered = sum(d['mastered'] for d in deck_stats)

        quiz_total = conn.execute("SELECT COUNT(*) as c FROM quiz_results").fetchone()['c']
        quiz_correct = conn.execute("SELECT SUM(is_correct) as c FROM quiz_results").fetchone()['c'] or 0

        progress = models.get_progress_history(7)
    finally:
        conn.close()

    today = datetime.now().strftime("%Y-%m-%d")

    print()
    print("  ╔═══════════════════════════════════════════════════╗")
    print("  ║           EngLearn Dashboard                      ║")
    print("  ╠═══════════════════════════════════════════════════╣")
    print(f"  ║  Date: {today}                              ║")
    print("  ╠═══════════════════════════════════════════════════╣")
    print("  ║                                                   ║")

    # Error rate
    error_rate = (total - correct) * 100 // total if total else 0
    print(f"  ║  Log: {total} entries  |  Error rate: {error_rate}%          ║"[:56] + "║")
    print("  ║                                                   ║")

    # Cards
    mastery_pct = mastered * 100 // total_cards if total_cards else 0
    print(f"  ║  Cards: {total_cards} total  |  {due_cards} due today            ║"[:56] + "║")
    print(f"  ║  Mastered: {mastered}/{total_cards} ({mastery_pct}%)                    ║"[:56] + "║")
    print("  ║                                                   ║")

    # Quiz
    quiz_acc = quiz_correct * 100 // quiz_total if quiz_total else 0
    print(f"  ║  Quizzes: {quiz_total} answered  |  Accuracy: {quiz_acc}%       ║"[:56] + "║")
    print("  ║                                                   ║")

    # Weekly activity
    print("  ║  This Week:                                       ║")
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    date_activity = {p['date']: p['cards_reviewed'] + p['quiz_taken'] for p in progress}
    week_line = "  ║  "
    for p in progress[-7:]:
        act = p['cards_reviewed'] + p['quiz_taken']
        if act > 10:
            week_line += "██ "
        elif act > 0:
            week_line += "▄▄ "
        else:
            week_line += "░░ "
    week_line = week_line.ljust(54) + "║"
    print(week_line)
    print("  ║                                                   ║")

    # Quick actions
    print("  ╠═══════════════════════════════════════════════════╣")
    print("  ║  Quick Actions:                                   ║")
    print("  ║    englearn review      - Review due flashcards   ║")
    print("  ║    englearn quiz        - Take a quiz             ║")
    print("  ║    englearn stats       - Detailed statistics     ║")
    print("  ║    englearn sync        - Import new errors       ║")
    print("  ╚═══════════════════════════════════════════════════╝")
    print()
