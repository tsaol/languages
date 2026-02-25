"""SM-2 Spaced Repetition Engine and flashcard review session."""
import os
import sys
from datetime import datetime
from englearn.db import models


QUALITY_MAP = {
    '1': (1, "Don't know"),
    '2': (3, 'Know it, but hesitated'),
    '3': (5, 'Easy'),
}


def clear_screen():
    os.system('clear' if os.name == 'posix' else 'cls')


def run_review(deck: str = None, limit: int = 20):
    """Run an interactive flashcard review session."""
    cards = models.get_due_flashcards(deck=deck, limit=limit)

    if not cards:
        print("\n  No cards due for review right now!")
        print("  Come back later or try: englearn review --all\n")
        return

    total = len(cards)
    correct = 0
    reviewed = 0

    print(f"\n  {'=' * 50}")
    deck_label = deck or "All Decks"
    print(f"  Flashcard Review | {deck_label} | {total} cards due")
    print(f"  {'=' * 50}\n")

    try:
        for i, card in enumerate(cards):
            # Progress bar
            progress = int((i / total) * 30)
            bar = '█' * progress + '░' * (30 - progress)
            print(f"  [{bar}] {i + 1}/{total}")
            print(f"  Deck: {card['deck']}")
            print(f"  {'─' * 50}")
            print()

            # Show front
            print(f"  📋 {card['front']}")
            print()

            if card['hint']:
                input("  Press Enter to see hint...")
                print(f"  💡 Hint: {card['hint']}")
                print()

            input("  Press Enter to reveal answer...")
            print()

            # Show back
            print(f"  ✅ {card['back']}")
            print()

            # Self-rating
            print("  Rate your recall:")
            for key, (score, desc) in QUALITY_MAP.items():
                print(f"    {key} - {desc}")
            print()

            while True:
                rating = input("  Your rating (1-3):").strip()
                if rating in QUALITY_MAP:
                    break
                print("  Please enter 1, 2, or 3.")

            quality = QUALITY_MAP[rating][0]
            models.update_flashcard_sm2(card['id'], quality)

            if quality >= 3:
                correct += 1
                print("  ✓ Good!")
            else:
                print("  ✗ Keep practicing this one.")

            reviewed += 1
            print()

    except (KeyboardInterrupt, EOFError):
        print("\n\n  Session interrupted.")

    # Session summary
    print(f"\n  {'=' * 50}")
    print(f"  Session Complete!")
    print(f"  {'─' * 50}")
    print(f"  Reviewed: {reviewed}/{total}")
    if reviewed > 0:
        pct = correct * 100 // reviewed
        print(f"  Correct:  {correct}/{reviewed} ({pct}%)")
    print(f"  {'=' * 50}\n")

    # Record progress
    models.record_daily_progress(cards_reviewed=reviewed, cards_correct=correct)


def run_review_all(deck: str = None, limit: int = 20):
    """Review cards regardless of schedule (for practice)."""
    from englearn.db.database import get_connection
    conn = get_connection()
    try:
        if deck:
            rows = conn.execute(
                "SELECT * FROM flashcards WHERE deck = ? ORDER BY RANDOM() LIMIT ?",
                (deck, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM flashcards ORDER BY RANDOM() LIMIT ?",
                (limit,)
            ).fetchall()
        cards = [dict(r) for r in rows]
    finally:
        conn.close()

    if not cards:
        print("\n  No flashcards found. Run 'englearn init' first.\n")
        return

    total = len(cards)
    correct = 0
    reviewed = 0

    print(f"\n  {'=' * 50}")
    print(f"  Practice Mode | {total} random cards")
    print(f"  {'=' * 50}\n")

    try:
        for i, card in enumerate(cards):
            progress = int((i / total) * 30)
            bar = '█' * progress + '░' * (30 - progress)
            print(f"  [{bar}] {i + 1}/{total}")
            print(f"  Deck: {card['deck']}")
            print(f"  {'─' * 50}")
            print()
            print(f"  📋 {card['front']}")
            print()

            input("  Press Enter to reveal answer...")
            print()
            print(f"  ✅ {card['back']}")
            print()

            while True:
                rating = input("  Did you know it? (y/n): ").strip().lower()
                if rating in ('y', 'n'):
                    break

            if rating == 'y':
                correct += 1
                models.update_flashcard_sm2(card['id'], 4)
            else:
                models.update_flashcard_sm2(card['id'], 1)

            reviewed += 1
            print()

    except (KeyboardInterrupt, EOFError):
        print("\n\n  Session interrupted.")

    print(f"\n  Practice Done! {correct}/{reviewed} correct.\n")
    models.record_daily_progress(cards_reviewed=reviewed, cards_correct=correct)
