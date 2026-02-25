"""Classify errors into actionable categories."""
import re
from typing import List


CATEGORY_RULES = [
    ('chinese_mix', lambda e: any('\u4e00' <= c <= '\u9fff' for c in e.original)),
    ('spelling', lambda e: _match_explanation(e, ['typo', 'spell', 'misspell', 'should be "'])),
    ('article', lambda e: _match_explanation(e, ['article', 'a/an', 'an issue', 'the ']) or
                           _match_explanation(e, ['a issue', 'an before vowel'])),
    ('preposition', lambda e: _match_explanation(e, ['preposition', '"on"', '"in"', '"at"', 'on github',
                                                      'focus on', 'install on', 'on ->', 'in ->'])),
    ('incomplete', lambda e: _match_explanation(e, ['incomplete', 'missing subject', 'missing verb',
                                                     'missing object', 'missing article'])),
    ('capitalization', lambda e: _match_explanation(e, ['capital', 'uppercase', 'lowercase', '"i" should'])),
    ('tense', lambda e: _match_explanation(e, ['tense', 'past tense', 'present tense', 'should be past',
                                                'check->checked'])),
    ('word_choice', lambda e: _match_explanation(e, ['word choice', 'more natural', 'better word',
                                                      'should use "'])),
    ('punctuation', lambda e: _match_explanation(e, ['punctuation', 'question mark', 'comma',
                                                      'apostrophe', "don't"])),
]


def _match_explanation(entry, keywords: List[str]) -> bool:
    exp = entry.explanation.lower()
    return any(kw.lower() in exp for kw in keywords)


def categorize(entry) -> List[str]:
    if entry.is_correct:
        return ['correct']
    categories = []
    for cat_name, rule in CATEGORY_RULES:
        try:
            if rule(entry):
                categories.append(cat_name)
        except Exception:
            pass
    return categories or ['other']
