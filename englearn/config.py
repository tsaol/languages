"""Paths and constants for EngLearn."""
import os

HOME = os.path.expanduser("~")
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "englearn.db")
LOG_PATH = os.path.join(HOME, "english.log")
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db", "schema.sql")

# SM-2 defaults
SM2_DEFAULT_EASE = 2.5
SM2_MIN_EASE = 1.3

# Quiz settings
DEFAULT_QUIZ_COUNT = 10
SIMILARITY_THRESHOLD_CORRECT = 0.80
SIMILARITY_THRESHOLD_PARTIAL = 0.60
