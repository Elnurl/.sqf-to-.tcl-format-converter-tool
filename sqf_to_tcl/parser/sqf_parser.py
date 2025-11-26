"""Simple SQF parser that emits a lightweight AST for basic constructs.

This is a pragmatic, regex/scan-based parser designed for the initial PoC.
It recognizes comments, assignments, if/then, for-from-to-do, while, hint, sleep,
and emits Unknown nodes for anything else.

The parser returns a list of Node dataclasses defined here.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import List, Union


@dataclass
class Node:
    kind: str
    raw: str
    data: dict


def _strip_semicolon(s: str) -> str:
    return s.rstrip().rstrip(';').strip()


def parse_sqf(source: str) -> List[Node]:
    """Parse SQF source into a list of Nodes.

    This is a forgiving parser: it splits top-level statements by semicolons
    while respecting braces, and classifies each statement.
    """
    statements: List[str] = []
    buf = []
    brace_level = 0
    i = 0
    while i < len(source):
        ch = source[i]
        buf.append(ch)
        if ch == '{':
            brace_level += 1
        elif ch == '}':
            brace_level = max(0, brace_level - 1)
        elif ch == ';' and brace_level == 0:
            # end of statement
            statements.append(''.join(buf).strip())
            buf = []
        i += 1
    # leftover
    leftover = ''.join(buf).strip()
    if leftover:
        statements.append(leftover)

    # Handle newline-separated comments or multi-line statements where comment
    # lines may not end with a semicolon by splitting those statements by lines
    processed_statements: List[str] = []
    for st in statements:
        # If this top-level statement contains braces, keep it whole so
        # block regexes (if/for/while) can match the body. Only split
        # multi-line text into individual lines when there are no braces.
        if '\n' in st and ('{' not in st and '}' not in st):
            for line in st.splitlines():
                l = line.strip()
                if not l:
                    continue
                processed_statements.append(l)
        else:
            processed_statements.append(st)

    nodes: List[Node] = []
    for st in processed_statements:
        s = st.strip()
        if not s:
            continue
        # comment: support // and lines starting with ';' (company-style)
        m = re.match(r'^//\s?(.*)$', s)
        if m:
            nodes.append(Node('Comment', s, {'text': m.group(1).strip()}))
            continue
        m2 = re.match(r'^;\s?(.*)$', s)
        if m2:
            nodes.append(Node('Comment', s, {'text': m2.group(1).strip()}))
            continue

        # assignment: _var = expr;  (direct)
        m = re.match(r'^_?([A-Za-z0-9_]+)\s*=\s*(.+);?$', s)
        if m:
            name = m.group(1)
            val = _strip_semicolon(m.group(2))
            nodes.append(Node('Assignment', s, {'name': name, 'value': val}))
            continue
        # fallback: allow assignments with a leading keyword, e.g. 'VERIFY  xx2 = tos_mode1 ;'
        if '=' in s:
            m = re.search(r'([A-Za-z0-9_]+)\s*=\s*(.+);?$', s)
            if m:
                name = m.group(1)
                val = _strip_semicolon(m.group(2))
                nodes.append(Node('Assignment', s, {'name': name, 'value': val}))
                continue

        # if (...) then { ... }
        m = re.match(r'^if\s*\((.+)\)\s*then\s*\{(.*)\}\s*;?$', s, re.S)
        if m:
            cond = m.group(1).strip()
            body = m.group(2).strip()
            nodes.append(Node('If', s, {'cond': cond, 'body': body}))
            continue

        # for "_i" from 0 to 3 do { ... }
        m = re.match(r'^for\s+"?_?([A-Za-z0-9_]+)"?\s+from\s+([0-9\-]+)\s+to\s+([0-9\-]+)\s+do\s*\{(.*)\}\s*;?$', s, re.S)
        if m:
            var = m.group(1)
            start = m.group(2)
            end = m.group(3)
            body = m.group(4).strip()
            nodes.append(Node('For', s, {'var': var, 'start': start, 'end': end, 'body': body}))
            continue

        # while {condition} do { body }
        m = re.match(r'^while\s*\{(.+)\}\s*do\s*\{(.*)\}\s*;?$', s, re.S)
        if m:
            cond = m.group(1).strip()
            body = m.group(2).strip()
            nodes.append(Node('While', s, {'cond': cond, 'body': body}))
            continue

        # hint "..." or hint format [...] ; or hint something
        m = re.match(r'^hint\s+(.+);?$', s, re.S)
        if m:
            payload = _strip_semicolon(m.group(1))
            nodes.append(Node('Hint', s, {'payload': payload}))
            continue

        # sleep N;
        m = re.match(r'^sleep\s+([0-9\.]+)\s*;?$', s)
        if m:
            nodes.append(Node('Sleep', s, {'seconds': m.group(1)}))
            continue

        # fallback unknown
        nodes.append(Node('Unknown', s, {'raw': s}))

    return nodes


if __name__ == '__main__':
    sample = '''// Example SQF
_value = 5;
if (_value > 3) then {
    hint "Value is high";
};
for "_i" from 0 to 3 do {
    hint format ["Index: %1", _i];
};
sleep 1;
'''
    for n in parse_sqf(sample):
        print(n)
