"""SM-2 Spaced Repetition Engine with typing-based review."""
import os
from datetime import datetime
from englearn.db import models


def clear_screen():
    os.system('clear' if os.name == 'posix' else 'cls')


def normalize(s):
    return s.lower().strip().replace("'", "'")


def check_match(user_answer, correct_answer):
    """Compare user answer with correct answer. Returns (match_type, rating)."""
    u = normalize(user_answer)
    c = normalize(correct_answer)
    if u == c:
        return 'exact', 5
    # Fuzzy: strip punctuation and extra spaces
    import re
    u_clean = re.sub(r'[^a-z0-9\s]', '', u).strip()
    c_clean = re.sub(r'[^a-z0-9\s]', '', c).strip()
    if u_clean == c_clean:
        return 'exact', 5
    if c_clean in u_clean or u_clean in c_clean:
        if len(u_clean) >= 3:
            return 'close', 3
    # Similarity check
    from difflib import SequenceMatcher
    sim = SequenceMatcher(None, u_clean, c_clean).ratio()
    if sim >= 0.85:
        return 'close', 3
    return 'wrong', 1


def run_review(deck: str = None, limit: int = 20):
    """Run an interactive typing-based flashcard review session."""
    cards = models.get_due_flashcards(deck=deck, limit=limit)

    if not cards:
        print("\n  No cards due for review right now!")
        print("  Come back later or try: englearn review --all\n")
        return

    total = len(cards)
    correct = 0
    reviewed = 0
    failed = []

    deck_label = deck or "All Decks"
    print(f"\n  {'=' * 50}")
    print(f"  Flashcard Review | {deck_label} | {total} cards due")
    print(f"  Type your answer. 'q' to quit, 's' to skip.")
    print(f"  {'=' * 50}\n")

    try:
        for i, card in enumerate(cards):
            progress = int((i / total) * 30)
            bar = '█' * progress + '░' * (30 - progress)
            print(f"  [{bar}] {i + 1}/{total}")
            print(f"  {'─' * 50}")
            print()
            print(f"  📋 {card['front']}")
            if card['hint']:
                print(f"  💡 {card['hint']}")
            print()

            user_input = input("  ✏️  Your answer: ").strip()

            if user_input.lower() == 'q':
                break

            if user_input.lower() == 's':
                print(f"\n  ⏭️  Skipped")
                print(f"  ✅ Answer: {card['back']}")
                models.update_flashcard_sm2(card['id'], 1)
                reviewed += 1
                failed.append(card)
                print()
                continue

            match_type, rating = check_match(user_input, card['back'])
            reviewed += 1

            print()
            if match_type == 'exact':
                print(f"  ✅ Correct!")
                correct += 1
            elif match_type == 'close':
                print(f"  ⚠️  Close!")
                print(f"  ✅ Answer: {card['back']}")
                correct += 1
            else:
                print(f"  ❌ Wrong")
                print(f"  Your answer: {user_input}")
                print(f"  ✅ Answer:    {card['back']}")
                failed.append(card)

            models.update_flashcard_sm2(card['id'], rating)
            print()

    except (KeyboardInterrupt, EOFError):
        print("\n\n  Session interrupted.")

    # Summary
    print(f"\n  {'=' * 50}")
    print(f"  Session Complete!")
    print(f"  {'─' * 50}")
    print(f"  Reviewed: {reviewed}/{total}")
    if reviewed > 0:
        pct = correct * 100 // reviewed
        print(f"  Correct:  {correct}/{reviewed} ({pct}%)")
    if failed:
        print(f"  Failed:   {len(failed)} cards")
    print(f"  {'=' * 50}\n")

    models.record_daily_progress(cards_reviewed=reviewed, cards_correct=correct)

    # Offer retry
    if failed:
        retry = input("  Retry failed cards? (y/n): ").strip().lower()
        if retry == 'y':
            _retry_cards(failed)


def _retry_cards(cards):
    """Retry failed cards."""
    total = len(cards)
    correct = 0
    print(f"\n  Retrying {total} failed cards...\n")

    try:
        for i, card in enumerate(cards):
            print(f"  [{i + 1}/{total}] {card['front']}")
            if card['hint']:
                print(f"  💡 {card['hint']}")

            user_input = input("  ✏️  Your answer: ").strip()
            if user_input.lower() == 'q':
                break

            match_type, rating = check_match(user_input, card['back'])
            if match_type in ('exact', 'close'):
                print(f"  ✅ Correct!")
                correct += 1
                models.update_flashcard_sm2(card['id'], rating)
            else:
                print(f"  ❌ Answer: {card['back']}")
                models.update_flashcard_sm2(card['id'], 1)
            print()

    except (KeyboardInterrupt, EOFError):
        print("\n  Interrupted.")

    print(f"  Retry done: {correct}/{total} correct.\n")


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
    print(f"  Type your answer. 'q' to quit, 's' to skip.")
    print(f"  {'=' * 50}\n")

    try:
        for i, card in enumerate(cards):
            progress = int((i / total) * 30)
            bar = '█' * progress + '░' * (30 - progress)
            print(f"  [{bar}] {i + 1}/{total}")
            print(f"  {'─' * 50}")
            print(f"  📋 {card['front']}")
            print()

            user_input = input("  ✏️  Your answer: ").strip()
            if user_input.lower() == 'q':
                break
            if user_input.lower() == 's':
                print(f"  ⏭️  Answer: {card['back']}\n")
                reviewed += 1
                continue

            match_type, rating = check_match(user_input, card['back'])
            reviewed += 1

            if match_type in ('exact', 'close'):
                print(f"  ✅ Correct!")
                correct += 1
                models.update_flashcard_sm2(card['id'], rating)
            else:
                print(f"  ❌ Answer: {card['back']}")
                models.update_flashcard_sm2(card['id'], 1)
            print()

    except (KeyboardInterrupt, EOFError):
        print("\n\n  Session interrupted.")

    print(f"\n  Practice Done! {correct}/{reviewed} correct.\n")
    models.record_daily_progress(cards_reviewed=reviewed, cards_correct=correct)
