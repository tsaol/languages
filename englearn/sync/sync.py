"""Sync new entries from english.log into the database."""
from englearn.config import LOG_PATH
from englearn.parser.log_parser import parse_log
from englearn.parser.categorizer import categorize
from englearn.db import models
from englearn.db.database import init_db
from englearn.flashcard.deck_manager import generate_all_decks


def full_sync():
    """Parse entire log and rebuild database."""
    init_db()

    print("  Parsing english.log...")
    entries = parse_log(LOG_PATH)
    print(f"  Found {len(entries)} entries.")

    correct = 0
    incorrect = 0
    for entry in entries:
        cats = categorize(entry)
        models.insert_entry(entry, cats)
        if entry.is_correct:
            correct += 1
        else:
            incorrect += 1

    models.set_sync_state('last_line', str(entries[-1].line_number if entries else 0))

    print(f"  Imported: {correct} correct, {incorrect} errors")
    print()

    # Generate flashcards
    print("  Generating flashcard decks...")
    counts = generate_all_decks()
    total_cards = sum(counts.values())
    print(f"  Created {total_cards} flashcards:")
    for deck, count in sorted(counts.items()):
        if count > 0:
            print(f"    {deck}: {count} cards")
    print()

    models.record_daily_progress(new_errors=incorrect)

    return len(entries)


def incremental_sync():
    """Only parse new entries since last sync."""
    init_db()

    last_line = models.get_sync_state('last_line')
    start = int(last_line) if last_line else 0

    if start == 0:
        return full_sync()

    print(f"  Syncing from line {start}...")
    entries = parse_log(LOG_PATH, start_line=start)

    if not entries:
        print("  No new entries found.")
        return 0

    new_errors = 0
    for entry in entries:
        cats = categorize(entry)
        models.insert_entry(entry, cats)
        if not entry.is_correct:
            new_errors += 1

    models.set_sync_state('last_line', str(entries[-1].line_number))
    print(f"  Imported {len(entries)} new entries ({new_errors} errors).")

    # Regenerate flashcards
    print("  Regenerating flashcards...")
    counts = generate_all_decks()
    total_cards = sum(counts.values())
    print(f"  Total flashcards: {total_cards}")

    models.record_daily_progress(new_errors=new_errors)

    return len(entries)
