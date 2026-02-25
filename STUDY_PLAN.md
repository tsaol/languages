# 4-Week English Study Plan

> Based on analysis of 835 daily interactions (as of 2026-02-25)

## Problem Diagnosis

| Priority | Problem | Rate | Description |
|----------|---------|------|-------------|
| **P0** | Chinese instead of English | 89% | Default to Chinese, not trying English |
| **P1** | Spelling/Typos | 13% | Typing too fast: hvae, thi, dowload |
| **P2** | Missing articles | 12% | a/an/the misuse or omitted |
| **P3** | Incomplete sentences | 5% | Missing subject, preposition, etc. |

## Week 1: Stop Using Chinese (P0)

**Goal**: 100% English in daily interaction, grammar mistakes are OK.

- Daily: `englearn review -d translate -n 10`
- Daily: `englearn quiz -t translate -n 5`
- Mindset: Don't be afraid of mistakes. Just write in English.

## Week 2: Fix Spelling (P1)

**Goal**: No more common typos.

- Daily: `englearn review -d spelling -n 15`
- Slow down when typing, proofread before sending.
- SM-2 algorithm will prioritize words you keep getting wrong.

## Week 3: Articles & Prepositions (P2 + P3)

**Goal**: Correct use of a/an/the and on/in/at.

- Daily: `englearn review -d fill_blank -n 10`
- Daily: `englearn review -d complete -n 10`
- Key rules:
  - Platforms use **on** (on GitHub, on AWS)
  - Install **on** a machine
  - Vowel sounds use **an** (an issue, an error)

## Week 4: Idiomatic Expressions (Polish)

**Goal**: Sound natural, not just grammatically correct.

- Daily: `englearn review -d pattern`
- Key patterns:
  - `Could you + verb + object?` (requests)
  - `I'd like to + verb` (expressing wants)
  - `Does it come with ...?` (asking about features)

## Daily Routine (~10-15 min)

```
Morning:  englearn review -n 15      ← Review due flashcards (5 min)
Daytime:  Interact with Claude in English  ← Real practice
Evening:  englearn quiz -n 10        ← Test yourself (5 min)
Before bed: englearn stats           ← Check progress
```

## Targets

| Metric | Now | Week 4 Target |
|--------|-----|---------------|
| Chinese usage | 89% | <50% |
| Log accuracy | 21% | 40%+ |
| Flashcards mastered | 0/764 | 150+ |
| Quiz accuracy | 0% | 50%+ |

## Commands Reference

```bash
englearn dashboard          # Overview panel
englearn review             # Review due flashcards (SM-2)
englearn review -d spelling # Review spelling deck only
englearn review --all       # Random practice (ignore schedule)
englearn quiz               # Mixed quiz
englearn quiz -t translate  # Translation quiz only
englearn quiz -n 20         # 20 questions
englearn stats              # Detailed statistics
englearn weak               # Show weakest areas
englearn search "keyword"   # Search error entries
englearn sync               # Import new errors from english.log
```
