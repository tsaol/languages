"""Main CLI entry point for EngLearn."""
import argparse
import sys


def cmd_init(args):
    """Initialize database and import all log entries."""
    from englearn.db.database import reset_db
    from englearn.sync.sync import full_sync

    print("\n  Initializing EngLearn...")
    print()
    reset_db()
    count = full_sync()
    print(f"  Done! {count} entries imported.")
    print("  Run 'englearn dashboard' to see your overview.")
    print("  Run 'englearn review' to start studying!\n")


def cmd_sync(args):
    """Sync new entries from english.log."""
    from englearn.sync.sync import incremental_sync
    print("\n  Syncing english.log...")
    incremental_sync()
    print()


def cmd_vocab(args):
    """Sync Notion vocabulary and create flashcards."""
    from englearn.sync.notion_sync import sync_notion_to_flashcards
    print("\n  Syncing Notion vocabulary...")
    sync_notion_to_flashcards()
    print()


def cmd_push(args):
    """Push progress to Notion."""
    from englearn.sync.progress_sync import push_progress
    print()
    push_progress()
    print()


def cmd_pull(args):
    """Pull progress from Notion."""
    from englearn.sync.progress_sync import pull_progress
    print()
    pull_progress()
    print()


def cmd_review(args):
    """Run flashcard review session."""
    from englearn.flashcard.engine import run_review, run_review_all
    if args.all:
        run_review_all(deck=args.deck, limit=args.count)
    else:
        run_review(deck=args.deck, limit=args.count)


def cmd_quiz(args):
    """Run interactive quiz."""
    from englearn.quiz.quiz_engine import run_quiz
    run_quiz(quiz_type=args.type, count=args.count)


def cmd_stats(args):
    """Show statistics."""
    from englearn.tracker.stats import show_stats
    show_stats(period_days=args.period)


def cmd_dashboard(args):
    """Show dashboard."""
    from englearn.tracker.dashboard import show_dashboard
    show_dashboard()


def cmd_decks(args):
    """List available decks and their stats."""
    from englearn.db.models import get_deck_stats
    stats = get_deck_stats()
    if not stats:
        print("\n  No decks found. Run 'englearn init' first.\n")
        return
    print(f"\n  {'Deck':<16} {'Total':>6} {'Due':>6} {'Mastered':>10}")
    print(f"  {'─' * 42}")
    for d in stats:
        print(f"  {d['deck']:<16} {d['total']:>6} {d['due']:>6} {d['mastered']:>10}")
    print()


def cmd_search(args):
    """Search through error entries."""
    from englearn.db.models import search_entries
    results = search_entries(args.keyword)
    if not results:
        print(f"\n  No entries found for '{args.keyword}'.\n")
        return
    print(f"\n  Found {len(results)} entries for '{args.keyword}':\n")
    for r in results[:20]:
        print(f"  [{r['timestamp'][:10]}] {r['status'].upper()}")
        print(f"    Original:  {r['original'][:80]}")
        if r['corrected'] and r['corrected'] != 'N/A':
            print(f"    Corrected: {r['corrected'][:80]}")
        print()


def cmd_talk(args):
    """Run conversation practice."""
    from englearn.quiz.conversation import run_conversation
    run_conversation(count=args.count)


def cmd_weak(args):
    """Show weakest areas."""
    from englearn.db.models import get_category_stats, get_weak_categories
    from englearn.tracker.stats import _category_display_name

    cat_stats = get_category_stats()
    print(f"\n  Your Error Categories (by frequency):")
    print(f"  {'─' * 45}")
    for cs in cat_stats:
        name = _category_display_name(cs['category'])
        print(f"    {name:<25} {cs['count']} errors")

    weak = get_weak_categories()
    if weak:
        print(f"\n  Lowest Quiz Accuracy:")
        print(f"  {'─' * 45}")
        for cat, acc in weak:
            name = _category_display_name(cat)
            print(f"    {name:<25} {acc:.0%}")

    print(f"\n  Recommendation: Focus on the top 2-3 categories.")
    print(f"  Try: englearn review --deck translate\n")


def main():
    parser = argparse.ArgumentParser(
        prog='englearn',
        description='Personal English Learning System'
    )
    sub = parser.add_subparsers(dest='command')

    # init
    sub.add_parser('init', help='Initialize and import all log entries')

    # sync
    sub.add_parser('sync', help='Sync new entries from english.log')

    # vocab
    sub.add_parser('vocab', help='Sync Notion vocabulary into flashcards')

    # push / pull
    sub.add_parser('push', help='Push progress to Notion (for cross-device sync)')
    sub.add_parser('pull', help='Pull progress from Notion (on new device)')

    # review
    p_review = sub.add_parser('review', help='Flashcard review session')
    p_review.add_argument('--deck', '-d', type=str, default=None,
                          help='Deck name (translate/spelling/fill_blank/complete/pattern)')
    p_review.add_argument('--count', '-n', type=int, default=20, help='Number of cards')
    p_review.add_argument('--all', action='store_true', help='Review all cards (not just due)')

    # quiz
    p_quiz = sub.add_parser('quiz', help='Interactive quiz')
    p_quiz.add_argument('--type', '-t', type=str, default='mixed',
                        choices=['mixed', 'translate', 'correct'],
                        help='Quiz type')
    p_quiz.add_argument('--count', '-n', type=int, default=10, help='Number of questions')

    # stats
    p_stats = sub.add_parser('stats', help='Show statistics')
    p_stats.add_argument('--period', '-p', type=int, default=30, help='Period in days')

    # dashboard
    sub.add_parser('dashboard', help='Show dashboard overview')

    # decks
    sub.add_parser('decks', help='List flashcard decks')

    # search
    p_search = sub.add_parser('search', help='Search error entries')
    p_search.add_argument('keyword', type=str, help='Search keyword')

    # talk
    p_talk = sub.add_parser('talk', help='Conversation practice (dialogue-based)')
    p_talk.add_argument('--count', '-n', type=int, default=10, help='Number of rounds')

    # weak
    sub.add_parser('weak', help='Show weakest areas')

    args = parser.parse_args()

    if not args.command:
        # Default: show dashboard
        try:
            from englearn.tracker.dashboard import show_dashboard
            show_dashboard()
        except Exception:
            parser.print_help()
        return

    commands = {
        'init': cmd_init,
        'sync': cmd_sync,
        'push': cmd_push,
        'pull': cmd_pull,
        'review': cmd_review,
        'quiz': cmd_quiz,
        'stats': cmd_stats,
        'dashboard': cmd_dashboard,
        'decks': cmd_decks,
        'search': cmd_search,
        'talk': cmd_talk,
        'vocab': cmd_vocab,
        'weak': cmd_weak,
    }
    commands[args.command](args)


if __name__ == '__main__':
    main()
