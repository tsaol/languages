"""Parse ~/english.log into structured records."""
import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class LogEntry:
    timestamp: datetime
    original: str
    status: str  # "correct" or "incorrect"
    corrected: str
    idiomatic: str
    explanation: str
    pattern: str
    tense: str
    line_number: int

    @property
    def is_correct(self) -> bool:
        return self.status == "correct"

    @property
    def has_chinese(self) -> bool:
        return any('\u4e00' <= c <= '\u9fff' for c in self.original)


def _strip_brackets(s: str) -> str:
    s = s.strip()
    if s.startswith('[') and s.endswith(']'):
        return s[1:-1].strip()
    return s


def _parse_line(line: str, line_number: int) -> Optional[LogEntry]:
    line = line.strip()
    if not line:
        return None

    # Extract timestamp
    ts_match = re.match(r'^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]\s*', line)
    if not ts_match:
        return None
    timestamp = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S")
    rest = line[ts_match.end():]

    # Parse fields using field names as anchors
    field_names = ['Original:', 'Status:', 'Corrected:', 'Idiomatic:', 'Explanation:', 'Pattern:', 'Tense:']
    positions = []
    for name in field_names:
        # Find the field name preceded by | or at start
        idx = rest.find(name)
        if idx >= 0:
            positions.append((idx, name))

    positions.sort(key=lambda x: x[0])

    fields = {}
    for i, (pos, name) in enumerate(positions):
        start = pos + len(name)
        if i + 1 < len(positions):
            end = positions[i + 1][0]
            # Remove trailing | separator
            value = rest[start:end].strip()
            if value.endswith('|'):
                value = value[:-1].strip()
        else:
            value = rest[start:].strip()
        fields[name] = _strip_brackets(value)

    original = fields.get('Original:', '')
    status_raw = fields.get('Status:', '').lower()
    status = 'correct' if 'correct' in status_raw and 'incorrect' not in status_raw else 'incorrect'
    corrected = fields.get('Corrected:', 'N/A')
    idiomatic = fields.get('Idiomatic:', 'N/A')
    explanation = fields.get('Explanation:', '')
    pattern = fields.get('Pattern:', '')
    tense = fields.get('Tense:', '')

    if not original or original == 'N/A':
        return None

    return LogEntry(
        timestamp=timestamp,
        original=original,
        status=status,
        corrected=corrected,
        idiomatic=idiomatic,
        explanation=explanation,
        pattern=pattern,
        tense=tense,
        line_number=line_number,
    )


def parse_log(filepath: str, start_line: int = 0) -> List[LogEntry]:
    entries = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            if i <= start_line:
                continue
            entry = _parse_line(line, i)
            if entry:
                entries.append(entry)
    return entries
