CREATE TABLE IF NOT EXISTS log_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    original TEXT NOT NULL,
    status TEXT NOT NULL,
    corrected TEXT,
    idiomatic TEXT,
    explanation TEXT,
    pattern TEXT,
    tense TEXT,
    line_number INTEGER UNIQUE,
    imported_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS entry_categories (
    entry_id INTEGER REFERENCES log_entries(id),
    category TEXT NOT NULL,
    PRIMARY KEY (entry_id, category)
);

CREATE TABLE IF NOT EXISTS vocabulary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wrong_form TEXT NOT NULL,
    correct_form TEXT NOT NULL,
    context TEXT,
    frequency INTEGER DEFAULT 1,
    category TEXT
);

CREATE TABLE IF NOT EXISTS flashcards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deck TEXT NOT NULL,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    hint TEXT,
    source_entry_id INTEGER REFERENCES log_entries(id),
    ease_factor REAL DEFAULT 2.5,
    interval_days INTEGER DEFAULT 0,
    repetitions INTEGER DEFAULT 0,
    next_review TEXT,
    last_review TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quiz_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_type TEXT NOT NULL,
    question TEXT NOT NULL,
    user_answer TEXT,
    correct_answer TEXT,
    is_correct INTEGER,
    flashcard_id INTEGER REFERENCES flashcards(id),
    completed_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_progress (
    date TEXT PRIMARY KEY,
    cards_reviewed INTEGER DEFAULT 0,
    cards_correct INTEGER DEFAULT 0,
    quiz_taken INTEGER DEFAULT 0,
    quiz_correct INTEGER DEFAULT 0,
    new_errors_imported INTEGER DEFAULT 0,
    streak_days INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_flashcards_deck ON flashcards(deck);
CREATE INDEX IF NOT EXISTS idx_flashcards_next_review ON flashcards(next_review);
CREATE INDEX IF NOT EXISTS idx_entry_categories ON entry_categories(category);
