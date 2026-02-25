"""Generate flashcard decks from parsed log entries."""
import re
import difflib
from typing import List, Tuple
from englearn.db import models
from englearn.db.database import get_connection


def generate_all_decks():
    """Generate all flashcard decks from log entries."""
    conn = get_connection()
    try:
        # Clear existing flashcards
        conn.execute("DELETE FROM flashcards")
        conn.commit()
    finally:
        conn.close()

    entries = models.get_all_entries(status='incorrect')
    seen_fronts = set()
    counts = {'express': 0, 'daily': 0}

    for entry in entries:
        original = entry['original']
        corrected = entry['corrected']
        idiomatic = entry['idiomatic']
        explanation = entry['explanation']
        entry_id = entry['id']

        if not corrected or corrected == 'N/A':
            continue

        # Get categories for this entry
        conn = get_connection()
        try:
            cats = [r['category'] for r in conn.execute(
                "SELECT category FROM entry_categories WHERE entry_id = ?", (entry_id,)
            ).fetchall()]
        finally:
            conn.close()

        # --- Deck: express (translate + pattern) ---
        if any('\u4e00' <= c <= '\u9fff' for c in original):
            front = original
            if front not in seen_fronts:
                seen_fronts.add(front)
                hint = _make_hint(idiomatic if idiomatic != 'N/A' else corrected)
                models.insert_flashcard(
                    deck='express',
                    front=f"Translate: {front}",
                    back=idiomatic if idiomatic != 'N/A' else corrected,
                    hint=hint,
                    source_entry_id=entry_id
                )
                counts['express'] += 1
            continue

        # --- Deck: daily (spelling + fill_blank + complete) ---
        typo_pairs = _extract_typos(original, corrected, explanation)
        for wrong, right in typo_pairs:
            key = f"spell:{wrong}"
            if key not in seen_fronts:
                seen_fronts.add(key)
                models.insert_flashcard(
                    deck='daily',
                    front=f"Correct the spelling: {wrong}",
                    back=right,
                    hint=f"Used in: {original[:60]}...",
                    source_entry_id=entry_id
                )
                counts['daily'] += 1

        if 'article' in cats or 'preposition' in cats:
            blank_q = _make_fill_blank(original, corrected, explanation)
            if blank_q:
                front, answer = blank_q
                key = f"blank:{front}"
                if key not in seen_fronts:
                    seen_fronts.add(key)
                    models.insert_flashcard(
                        deck='daily',
                        front=front,
                        back=answer,
                        hint=explanation[:80],
                        source_entry_id=entry_id
                    )
                    counts['daily'] += 1

        if 'incomplete' in cats or 'other' in cats:
            front = f"Fix this sentence: {original}"
            if front not in seen_fronts:
                seen_fronts.add(front)
                models.insert_flashcard(
                    deck='daily',
                    front=front,
                    back=idiomatic if idiomatic != 'N/A' else corrected,
                    hint=explanation[:80],
                    source_entry_id=entry_id
                )
                counts['daily'] += 1

        # Pattern also goes to express
        pattern = entry.get('pattern', '')
        if pattern and pattern != 'N/A':
            key = f"pattern:{pattern[:50]}"
            if key not in seen_fronts:
                seen_fronts.add(key)
                models.insert_flashcard(
                    deck='express',
                    front=f"Use this pattern in a sentence: {pattern}",
                    back=idiomatic if idiomatic != 'N/A' else corrected,
                    hint=f"Example context: {explanation[:60]}",
                    source_entry_id=entry_id
                )
                counts['express'] += 1

    return counts


def _make_hint(text: str) -> str:
    """Create a hint by showing first word and blanking the rest."""
    words = text.split()
    if len(words) <= 2:
        return words[0] + " ..." if words else ""
    return f"{words[0]} {words[1]} ... {words[-1]}"


def _is_junk_spelling(wrong: str, right: str) -> bool:
    """Filter out non-spelling junk pairs."""
    wrong_c = wrong.lower().strip('.,?!:;')
    right_c = right.lower().strip('.,?!:;')

    # Same word (just punctuation diff)
    if wrong_c == right_c:
        return True

    # Too short to be meaningful
    if len(wrong_c) <= 2 or len(right_c) <= 2:
        return True

    # Technical terms / proper nouns that don't need spelling practice
    junk_words = {
        's3', 'aws', 'ec2', 'url', 'api', 'sdk', 'cli', 'ssh', 'cdn',
        'json', 'yaml', 'html', 'css', 'jsx', 'tsx', 'sql', 'pdf',
        'github', 'claude', 'tavily', 'perplexity', 'zhihu', 'toutiao',
        'cloudwatch', 'sagemaker', 'bedrock', 'litellm', 'openai',
        'hottrend', 'openclaw', 'mcp', 'llm', 'gpt',
    }
    if wrong_c in junk_words or right_c in junk_words:
        return True

    # Grammar changes, not spelling (tense, form changes)
    grammar_pairs = {
        ('check', 'checked'), ('upload', 'uploaded'), ('merge', 'merged'),
        ('sync', 'synced'), ('deploy', 'deployed'), ('name', 'named'),
        ('detail', 'detailed'), ('monitor', 'monitoring'), ('track', 'tracks'),
        ('write', 'writing'), ('in', 'on'), ('to', 'into'), ('a', 'an'),
        ('an', 'and'), ('would', 'could'), ('are', 'is'), ('have', 'have'),
        ('any', 'anything'), ('set', 'i'), ('red', 'read'),
        ('ok', 'ok'), ('codes', 'code'), ('list', 'list'),
    }
    if (wrong_c, right_c) in grammar_pairs or (right_c, wrong_c) in grammar_pairs:
        return True

    # Not a real typo if edit distance is too large relative to word length
    if _is_typo(wrong_c, right_c) is False:
        return True

    return False


def _extract_typos(original: str, corrected: str, explanation: str) -> List[Tuple[str, str]]:
    """Extract typo word pairs from original vs corrected."""
    pairs = []
    # Try to find explicit typo mentions in explanation
    typo_patterns = [
        r'"(\w+)"\s*(?:->|→|should be)\s*"(\w+)"',
        r'(\w+)\s*(?:->|→)\s*(\w+)',
    ]
    for pat in typo_patterns:
        for m in re.finditer(pat, explanation):
            wrong, right = m.group(1), m.group(2)
            if wrong.lower() != right.lower() and len(wrong) > 1:
                if not _is_junk_spelling(wrong, right):
                    pairs.append((wrong, right))

    if not pairs:
        # Word-level diff
        orig_words = original.lower().split()
        corr_words = corrected.lower().split()
        sm = difflib.SequenceMatcher(None, orig_words, corr_words)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == 'replace':
                for ow, cw in zip(orig_words[i1:i2], corr_words[j1:j2]):
                    if ow != cw and len(ow) > 1 and _is_typo(ow, cw) and not _is_junk_spelling(ow, cw):
                        pairs.append((ow, cw))
    return pairs


def _is_typo(a: str, b: str) -> bool:
    """Check if a is likely a typo of b (high similarity)."""
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    return ratio > 0.5 and ratio < 1.0


def _make_fill_blank(original: str, corrected: str, explanation: str) -> Tuple[str, str]:
    """Create a fill-in-the-blank question for article/preposition errors."""
    orig_words = original.split()
    corr_words = corrected.split()

    sm = difflib.SequenceMatcher(None, [w.lower() for w in orig_words],
                                  [w.lower() for w in corr_words])
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'insert':
            inserted = corr_words[j1:j2]
            for word in inserted:
                if word.lower() in ('a', 'an', 'the', 'on', 'in', 'at', 'for', 'to', 'of', 'with'):
                    blank_sentence = corr_words[:j1] + ['___'] + corr_words[j2:]
                    return (f"Fill the blank: {' '.join(blank_sentence)}", word)
        elif op == 'replace':
            for ow, cw in zip(orig_words[i1:i2], corr_words[j1:j2]):
                if cw.lower() in ('a', 'an', 'the', 'on', 'in', 'at', 'for', 'to', 'of', 'with'):
                    blank_sentence = list(corr_words)
                    idx = j1
                    if idx < len(blank_sentence):
                        blank_sentence[idx] = '___'
                    return (f"Fill the blank: {' '.join(blank_sentence)}", cw)
    return None
