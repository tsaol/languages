# EngLearn

Personal English learning system powered by SM-2 spaced repetition and LLM scoring. Built from real daily interaction errors.

## Install

```bash
pip install git+https://github.com/tsaol/languages.git
```

## CLI Usage

```bash
englearn login                # login to web server (first time only)
englearn                      # show stats (default)
englearn cards                # flashcard practice (type answers)
englearn cards -d vocab       # vocab deck only
englearn talk                 # conversation practice (LLM scored)
englearn talk -n 5            # 5 rounds only
englearn talk --all           # practice even if all done today
englearn stats                # learning statistics
englearn vocab "negotiate"    # save a word (auto-translates to Chinese)
englearn config               # show/set config (server URL)
```

## Web UI

Deployed at `http://<server>:5555` with dark theme, mobile-first design.

Pages: Review, Talk, Vocab, Stats

## Architecture

```
CLI (thin client)  ──HTTP──>  Flask Web Server  ──>  SQLite DB
                                    ↑                    ↓
Web Browser  ───────────────────────┘             Kimi K2.5 (Bedrock)
```

- **CLI**: Pure HTTP frontend, no direct DB access
- **Web API**: Flask app with JSON endpoints + HTML templates
- **LLM Scoring**: Kimi K2.5 on Amazon Bedrock for 6-dimension evaluation
- **SM-2 Engine**: Spaced repetition for flashcards and talk scenarios
- **Parser**: Extracts errors from ~/english.log

## Features

- Typing-based flashcard review with auto-compare
- Talk practice with LLM scoring (grammar, meaning, tone, fluency, pattern, vocabulary)
- Error highlights with colored underlines
- Any word tappable to save to Vocab (auto-translates)
- Server-side session persistence
- Dynamic scenario generation from your errors
- Stats dashboard with today's activity and streak

## Data

- Server: `data/englearn.db` (SQLite)
- Config: `~/.englearn_cli.json` (session cookies)
