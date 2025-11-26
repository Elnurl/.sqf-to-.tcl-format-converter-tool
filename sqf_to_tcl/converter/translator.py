"""Translator that converts the lightweight SQF AST (from parser) into TCL code.

This module focuses on rules in the user's prompt: variable assignments, if,
for-from-to-do, while, hint->puts, sleep->after, and comments.
"""
from __future__ import annotations
from typing import List
import re
from pathlib import Path
from textwrap import indent

from ..parser.sqf_parser import Node, parse_sqf


def _sqf_var_to_tcl(v: str) -> str:
    # Remove leading underscore if present and prefix with $ for expressions
    return ('$' + v.lstrip('_'))


def _translate_expr(expr: str) -> str:
    """Do small expression conversions: replace _var with $var and keep operators."""
    # Replace _name with $name
    expr = re.sub(r'_([A-Za-z0-9_]+)', r'\1', expr)
    # Replace variable references with $var when used bare (simple heuristic)
    expr = re.sub(r'\b([A-Za-z0-9_]+)\b', lambda m: ('$' + m.group(1)) if not re.match(r'^[0-9]+$', m.group(1)) else m.group(1), expr)
    # Fix accidental $$
    expr = expr.replace('$$', '$')
    return expr


def translate_nodes(nodes: List[Node], debug: bool = False) -> str:
    lines: List[str] = []
    for node in nodes:
        if node.kind == 'Comment':
            lines.append('# ' + node.data.get('text', '').strip())
        elif node.kind == 'Assignment':
            name = node.data['name'].lstrip('_')
            val = node.data['value']
            lines.append(f'set {name} {val}')
        elif node.kind == 'If':
            cond = node.data['cond']
            body = node.data['body']
            cond_tcl = _translate_expr(cond)
            # translate body recursively
            inner = translate_text_block(body)
            lines.append(f'if {{{cond_tcl}}} {{')
            lines.extend([indent(l, '    ') for l in inner.splitlines() if l.strip() != ''])
            lines.append('}')
        elif node.kind == 'For':
            var = node.data['var'].lstrip('_')
            start = node.data['start']
            end = node.data['end']
            body = node.data['body']
            inner = translate_text_block(body)
            # for {set i 0} {$i <= 3} {incr i} {
            lines.append(f'for {{set {var} {start}}} {{${var} <= {end}}} {{incr {var}}} {{')
            # body
            lines.extend([indent(l, '    ') for l in inner.splitlines() if l.strip() != ''])
            lines.append('}')
        elif node.kind == 'While':
            cond = _translate_expr(node.data['cond'])
            inner = translate_text_block(node.data['body'])
            lines.append(f'while {{{cond}}} {{')
            lines.extend([indent(l, '    ') for l in inner.splitlines() if l.strip() != ''])
            lines.append('}')
        elif node.kind == 'Hint':
            payload = node.data['payload']
            # handle format ["Index: %1", _i] or simple strings
            m = re.match(r'format\s*\[(.+)\]\s*', payload, re.S)
            if m:
                inner = m.group(1).strip()
                # split by comma
                parts = [p.strip() for p in re.split(r',\s*', inner, maxsplit=1)]
                fmt = parts[0].strip()
                fmt = fmt.strip('"')
                if len(parts) > 1:
                    varpart = re.sub(r'_([A-Za-z0-9_]+)', r'\1', parts[1])
                    varname = varpart.strip()
                    replacement = fmt.replace('%1', f'${varname}')
                    lines.append(f'puts "{replacement}"')
                else:
                    lines.append(f'puts "{fmt}"')
            else:
                # plain payload
                lines.append(f'puts {payload}')
        elif node.kind == 'Sleep':
            secs = float(node.data['seconds'])
            ms = int(secs * 1000)
            lines.append(f'after {ms}')
        else:
            # Unknown node: output a TODO comment and include raw
            lines.append(f"# TODO: Could not automatically translate: {node.raw}")
    return '\n'.join(lines)


def translate_text_block(text: str) -> str:
    """Translate a text block which may contain multiple SQF statements separated by semicolons."""
    from ..parser.sqf_parser import parse_sqf

    nodes = parse_sqf(text)
    return translate_nodes(nodes)


def convert_sqf_string_to_tcl(source: str, debug: bool = False, report: bool | None = None, rules_path: str | None = None) -> str:
    # Auto-detect special TOS_COM-style files (report format) and convert to that
    # report override precedence: explicit report flag > provided rules file > auto-detect
    use_report = False
    if report is True:
        use_report = True
    elif rules_path:
        use_report = True
    elif report is None and ('TOS_COM' in source or 'TOS_COM.sqf' in source):
        use_report = True

    if use_report:
        return convert_sqf_to_report(source, rules_path)

    nodes = parse_sqf(source)
    return translate_nodes(nodes, debug=debug)


def convert_sqf_to_report(source: str, rules_path: str | None = None) -> str:
    """Convert company-style SQF/comments into the formatted report output.

    Rules implemented (from your example):
    - Lines containing 'TOS_COM' create a header '0.1 TOS_COM'
    - Lines starting with 'vehicle' are titles and ignored
    - Lines like 'C <name> ; <text>' become entries under 'Send commands'
    - Lines containing 'VERIFY' and '=' become entries under 'Verify Telemetry' with
      format: '<var>: state :: Cnt <label> := <value>' where <label> is the comment after ';'
    - 'END' signals the end section
    """
    # Load rules.yaml if present (either provided or project default)
    rules = None
    resolved_rules_path = None
    if rules_path:
        resolved_rules_path = Path(rules_path)
    else:
        resolved_rules_path = Path(__file__).resolve().parent.parent / 'rules.yaml'

    if resolved_rules_path and resolved_rules_path.exists():
        try:
            import yaml as _yaml
        except Exception:
            _yaml = None
        if _yaml:
            try:
                with open(resolved_rules_path, 'r', encoding='utf-8') as f:
                    rules = _yaml.safe_load(f)
            except Exception:
                rules = None

    send_cmds = []
    verifies = []
    has_header = False
    seen_end = False

    for raw in source.splitlines():
        line = raw.strip()
        if not line:
            continue
        clean = line
        if clean.startswith(';'):
            clean = clean.lstrip(';').strip()

        # header detection via rules or default
        if rules and 'header' in rules:
            for h in rules['header']:
                if h.get('match') and h['match'] in line:
                    has_header = True
        else:
            if clean.upper().startswith('TOS_COM'):
                has_header = True

        # titles
        ignored = False
        if rules and 'titles' in rules:
            for pat in rules['titles']:
                if re.match(pat, clean, re.I):
                    ignored = True
        else:
            if clean.upper().startswith('VEHICLE'):
                ignored = True
        if ignored:
            continue

        # send command via rules or default C pattern
        handled = False
        if rules and 'send_command' in rules:
            pat = rules['send_command']['pattern']
            m = re.match(pat, line)
            if m:
                fmt = rules['send_command'].get('format', '{name} {text}')
                send_cmds.append(fmt.format(**m.groupdict()))
                handled = True
        if not handled:
            m = re.match(r'^C\s+([A-Za-z0-9_]+)\s*(?:;\s*(.+))?$', line, re.I)
            if m:
                name = m.group(1)
                comment = (m.group(2) or '').strip()
                send_cmds.append((name, comment))
                continue

        # verify
        if 'VERIFY' in clean.upper() and '=' in clean:
            if rules and 'verify' in rules:
                pat = rules['verify']['pattern']
                mm = re.search(pat, clean)
                if mm:
                    fmt = rules['verify'].get('format', '{var} {val} {label}')
                    verifies.append(fmt.format(**mm.groupdict()))
                    continue
            mm = re.search(r'([A-Za-z0-9_]+)\s*=\s*([A-Za-z0-9_]+)\s*(?:;\s*(.+))?$', clean)
            if mm:
                var = mm.group(1)
                val = mm.group(2)
                label = (mm.group(3) or '').strip()
                verifies.append((var, label, val))
                continue

        if clean.upper() == 'END':
            seen_end = True
            continue

    # Build output lines respecting whether send_cmds/verifies are tuples (default) or formatted strings (rules)
    out_lines = []
    if has_header:
        # if header text is in rules, use it
        if rules and 'header' in rules and isinstance(rules['header'], list) and len(rules['header']) > 0:
            out_lines.append(rules['header'][0].get('text', '0.1 TOS_COM'))
        else:
            out_lines.append('0.1 TOS_COM')
    if send_cmds:
        out_lines.append('    Send commands')
        for sc in send_cmds:
            if isinstance(sc, tuple):
                name, comment = sc
                out_lines.append(f'        {name}     {comment}')
            else:
                out_lines.append(sc)
    if verifies:
        out_lines.append('    Verify Telemetry')
        for v in verifies:
            if isinstance(v, tuple):
                var, label, val = v
                out_lines.append(f'            {var}: state :: Cnt {label} := {val} ')
            else:
                out_lines.append(v)
        out_lines.append('        ')
    if seen_end:
        out_lines.append('        END')

    return '\n'.join(out_lines)


def save_tcl_output(code: str, output_path: str) -> None:
    p = Path(output_path)
    p.write_text(code, encoding='utf-8')


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
    print(convert_sqf_string_to_tcl(sample))
