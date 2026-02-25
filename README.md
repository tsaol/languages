# EngLearn

Personal English learning system powered by SM-2 spaced repetition. Built from real daily interaction errors.

## Quick Start

```bash
git clone https://github.com/tsaol/languages.git
cd languages
pip install -e .
englearn init        # import english.log + generate flashcards
englearn vocab       # sync Notion vocabulary
englearn pull        # pull progress from Notion (if switching devices)
```

## Usage

### CLI Shortcuts

```bash
elv     # review vocab (10 cards)
ele     # review expressions (10 cards)
elr     # review all due cards (15 cards)
elt     # conversation practice (5 rounds)
elq     # quiz (10 questions)
eld     # dashboard
```

### Full Commands

```bash
englearn dashboard        # overview panel
englearn review           # review due flashcards
englearn review -d vocab  # review specific deck
englearn quiz             # take a quiz
englearn talk             # conversation practice
englearn stats            # detailed statistics
englearn weak             # show weakest areas
englearn search "word"    # search entries
englearn sync             # import new errors from english.log
englearn vocab            # sync Notion vocabulary
englearn push             # push progress to Notion
englearn pull             # pull progress from Notion
```

### Web UI

```bash
python3 web/app.py        # start on http://localhost:5555
```

## 3 Decks

| Deck | Cards | Content |
|------|-------|---------|
| daily | 88 | Spelling, articles, sentence completion |
| express | 659 | Translation, sentence patterns |
| vocab | 147 | Curated work vocabulary from Notion |

## Architecture

- **Parser**: Extracts errors from ~/english.log
- **SM-2 Engine**: Spaced repetition for flashcard scheduling
- **Notion Sync**: Two-way sync for vocabulary and progress
- **Web UI**: Flask app with dark theme, mobile-friendly
- **Cron**: Daily auto-sync at 6am

## Data

- Local: `data/englearn.db` (SQLite)
- Cloud: Notion "English Vocabulary" + "Study Progress" databases
