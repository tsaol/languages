"""Interactive quiz session controller."""
import os
import random
import difflib
from englearn.db import models
from englearn.db.database import get_connection
from englearn.config import SIMILARITY_THRESHOLD_CORRECT, SIMILARITY_THRESHOLD_PARTIAL


def clear_screen():
    os.system('clear' if os.name == 'posix' else 'cls')


def run_quiz(quiz_type: str = 'mixed', count: int = 10):
    """Run an interactive quiz session."""
    entries = models.get_all_entries(status='incorrect')
    if not entries:
        print("\n  No error entries found. Run 'englearn init' first.\n")
        return

    # Select questions based on type
    if quiz_type == 'translate':
        pool = [e for e in entries if any('\u4e00' <= c <= '\u9fff' for c in e['original'])]
    elif quiz_type == 'correct':
        pool = [e for e in entries if not any('\u4e00' <= c <= '\u9fff' for c in e['original'])]
    elif quiz_type == 'mixed':
        pool = entries
    else:
        pool = entries

    if not pool:
        print(f"\n  No questions available for type '{quiz_type}'.\n")
        return

    questions = random.sample(pool, min(count, len(pool)))
    total = len(questions)
    correct_count = 0

    print(f"\n  {'═' * 55}")
    print(f"   English Practice Quiz | {quiz_type.upper()} | {total} questions")
    print(f"  {'═' * 55}\n")

    try:
        for i, entry in enumerate(questions):
            has_chinese = any('\u4e00' <= c <= '\u9fff' for c in entry['original'])

            print(f"  Question {i + 1}/{total}  |  Score: {correct_count}/{i}")
            print(f"  {'─' * 55}")
            print()

            if has_chinese:
                # Translation question
                print("  [Translate to English]")
                print()
                print(f"  {entry['original']}")
                print()
                user_answer = input("  Your answer: ").strip()
            else:
                # Correct the error question
                print("  [Correct the Error]")
                print()
                print(f"  ❌ {entry['original']}")
                print()
                user_answer = input("  Your correction: ").strip()

            # Evaluate answer
            expected = entry['idiomatic'] if entry['idiomatic'] != 'N/A' else entry['corrected']
            alt_expected = entry['corrected']

            similarity1 = difflib.SequenceMatcher(None, user_answer.lower(), expected.lower()).ratio()
            similarity2 = difflib.SequenceMatcher(None, user_answer.lower(), alt_expected.lower()).ratio()
            best_sim = max(similarity1, similarity2)

            print()
            if best_sim >= SIMILARITY_THRESHOLD_CORRECT:
                print("  ✅ Correct!")
                correct_count += 1
                is_correct = True
            elif best_sim >= SIMILARITY_THRESHOLD_PARTIAL:
                print("  ⚠️  Close, but not quite.")
                is_correct = False
            else:
                print("  ❌ Not quite right.")
                is_correct = False

            print()
            print(f"  Your answer:   {user_answer}")
            print(f"  Correct:       {alt_expected}")
            if entry['idiomatic'] != 'N/A' and entry['idiomatic'] != alt_expected:
                print(f"  Idiomatic:     {entry['idiomatic']}")
            print(f"  Explanation:   {entry['explanation'][:100]}")

            if entry['pattern'] and entry['pattern'] != 'N/A':
                print(f"  Pattern:       {entry['pattern'][:80]}")

            # Record result
            models.record_quiz_result(
                quiz_type='translate' if has_chinese else 'correct_error',
                question=entry['original'],
                user_answer=user_answer,
                correct_answer=expected,
                is_correct=is_correct,
            )

            print()
            input("  Press Enter for next question...")
            print()

    except (KeyboardInterrupt, EOFError):
        print("\n\n  Quiz interrupted.")

    # Summary
    print(f"\n  {'═' * 55}")
    print(f"  Quiz Complete!")
    print(f"  {'─' * 55}")
    answered = min(i + 1, total) if 'i' in dir() else 0
    print(f"  Score: {correct_count}/{answered}")
    if answered > 0:
        pct = correct_count * 100 // answered
        print(f"  Accuracy: {pct}%")
        if pct >= 80:
            print("  Great job! Keep it up!")
        elif pct >= 50:
            print("  Not bad, but room for improvement.")
        else:
            print("  Keep practicing! Review your flashcards.")
    print(f"  {'═' * 55}\n")

    models.record_daily_progress(quiz_taken=answered, quiz_correct=correct_count)
