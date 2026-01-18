"""Translator that converts the lightweight SQF AST (from parser) into TCL code.

This module focuses on rules in the user's prompt: variable assignments, if,
for-from-to-do, while, hint->puts, sleep->after, and comments.
"""
from __future__ import annotations
from typing import List, Optional
import re
from pathlib import Path
from textwrap import indent

# Support both relative and absolute imports for flexibility
try:
    from ..parser.sqf_parser import Node, parse_sqf
except ImportError:
    # Fallback to absolute import when run directly or as standalone
    from sqf_to_tcl.parser.sqf_parser import Node, parse_sqf


def _detect_encoding(file_path: Path) -> str:
    """Try to detect file encoding automatically."""
    encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'ascii', 'utf-16']
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                f.read(1024)  # Try to read first 1KB
            return encoding
        except (UnicodeDecodeError, UnicodeError):
            continue
    
    # Fallback to utf-8
    return 'utf-8'


def load_argument_database(db_path: str, field_order: str = "command_priority_argument", validation_pattern: str | None = None, min_fields: int = 3) -> tuple[dict, list[str]]:
    """Load command argument definitions from a .txt database file.
    
    Universal parser that supports:
    - Auto-detection of encoding (UTF-8, Latin-1, ASCII, etc.)
    - Configurable field order (default: command priority argument)
    - Format validation using regex patterns from rules.yaml
    - Flexible parsing with whitespace handling
    - Comments support (# at start of line)
    - Empty lines ignored
    
    Args:
        db_path: Path to database .txt file
        field_order: Field order specification (default: "command_priority_argument")
                    Options: "command_priority_argument", "priority_command_argument", etc.
        validation_pattern: Optional regex pattern to validate each line format
        min_fields: Minimum number of fields required (default: 3)
    
    Expected format: <command_name> <priority_index> <argument_name>
    Examples:
        CM00001 3 IRU_Drft_Bias
        TC74111 4 Block_ID
        TC74111 3 Block_Offset
    
    Returns: (cmd_args_dict, validation_errors)
        cmd_args_dict: {cmd_name: {priority_index: arg_name}}
        validation_errors: List of validation error messages for invalid lines
    """
    cmd_args = {}
    validation_errors = []
    db_file = Path(db_path)
    
    if not db_file.exists():
        return cmd_args, validation_errors
    
    # Auto-detect encoding
    encoding = _detect_encoding(db_file)
    
    # Compile validation pattern if provided
    validation_re = None
    if validation_pattern:
        try:
            validation_re = re.compile(validation_pattern)
        except re.error:
            validation_re = None  # Invalid pattern, skip validation
    
    try:
        with open(db_file, 'r', encoding=encoding) as f:
            for line_num, line in enumerate(f, 1):
                original_line = line
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Validate format if pattern provided
                if validation_re:
                    if not validation_re.match(line):
                        validation_errors.append(f"Line {line_num}: Invalid format - {line[:50]}")
                        continue
                
                # Parse: command priority argument (default order)
                # Support multiple spaces/tabs as separators
                parts = line.split()
                
                # Check minimum fields requirement
                if len(parts) < min_fields:
                    validation_errors.append(f"Line {line_num}: Too few fields (expected {min_fields}, got {len(parts)}) - {line[:50]}")
                    continue
                
                if len(parts) >= 3:
                    # Default order: command priority argument
                    if field_order == "command_priority_argument":
                        cmd_name = parts[0]
                        try:
                            priority_idx = int(parts[1])
                            arg_name = ' '.join(parts[2:])  # Join remaining parts as argument name (in case it has spaces)
                        except (ValueError, IndexError):
                            validation_errors.append(f"Line {line_num}: Invalid priority index - {line[:50]}")
                            continue
                    elif field_order == "priority_command_argument":
                        try:
                            priority_idx = int(parts[0])
                            cmd_name = parts[1]
                            arg_name = ' '.join(parts[2:])
                        except (ValueError, IndexError):
                            validation_errors.append(f"Line {line_num}: Invalid priority index - {line[:50]}")
                            continue
                    else:
                        # Default to command_priority_argument
                        cmd_name = parts[0]
                        try:
                            priority_idx = int(parts[1])
                            arg_name = ' '.join(parts[2:])
                        except (ValueError, IndexError):
                            validation_errors.append(f"Line {line_num}: Invalid priority index - {line[:50]}")
                            continue
                    
                    # Store in dictionary
                    if cmd_name not in cmd_args:
                        cmd_args[cmd_name] = {}
                    cmd_args[cmd_name][priority_idx] = arg_name
                    
                elif len(parts) == 2:
                    # Handle case where priority might be missing (optional)
                    # Format: command argument (no priority)
                    if min_fields <= 2:
                        cmd_name = parts[0]
                        arg_name = parts[1]
                        # Use default priority 0 if priority is missing
                        if cmd_name not in cmd_args:
                            cmd_args[cmd_name] = {}
                        cmd_args[cmd_name][0] = arg_name
                    else:
                        validation_errors.append(f"Line {line_num}: Missing priority field - {line[:50]}")
                    
    except Exception as e:
        validation_errors.append(f"Error reading database file: {str(e)}")
    
    return cmd_args, validation_errors


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
    # Use parse_sqf that was already imported at module level
    nodes = parse_sqf(text)
    return translate_nodes(nodes)


def convert_sqf_string_to_tcl(source: str, debug: bool = False, report: bool | None = None, rules_path: str | None = None, db_path: str | None = None) -> str:
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
        return convert_sqf_to_report(source, rules_path, db_path)

    nodes = parse_sqf(source)
    return translate_nodes(nodes, debug=debug)


def convert_sqf_to_report(source: str, rules_path: str | None = None, db_path: str | None = None) -> str:
    """Convert company-style SQF/comments into the formatted report output.

    Rules implemented (from your example):
    - Lines containing 'TOS_COM' create a header '0.1 TOS_COM'
    - Lines starting with 'vehicle' are titles and ignored
    - Lines like 'C <name> ; <text>' become entries under 'Send commands'
    - Lines like 'C CM00001 0x1 0xcf' parse command with priority-indexed arguments
    - Lines like 'CM00001 3 IRU_Drft_Bias' define command arguments with priority indices
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

    # Load argument database if provided
    cmd_args = {}
    db_field_order = "command_priority_argument"  # Default field order
    validation_pattern = None
    min_fields = 3
    auto_lookup_enabled = True
    command_detection_patterns = []
    
    # Check if rules specify database format
    if rules and 'database' in rules:
        db_config = rules.get('database', {})
        db_field_order = db_config.get('field_order', 'command_priority_argument')
        validation_pattern = db_config.get('validation_pattern')
        min_fields = db_config.get('min_fields', 3)
        
        # Get auto-lookup settings
        auto_lookup_config = db_config.get('auto_lookup', {})
        auto_lookup_enabled = auto_lookup_config.get('enabled', True)
        command_detection_patterns = db_config.get('command_detection_patterns', [])
    
    if db_path:
        cmd_args, validation_errors = load_argument_database(
            db_path, 
            field_order=db_field_order,
            validation_pattern=validation_pattern,
            min_fields=min_fields
        )
        # Store validation errors for potential reporting (could be used in GUI)
        if validation_errors:
            # For now, silently skip validation errors, but they're available for future use
            pass
    
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

        # Parse command argument definitions: CM00001 3 IRU_Drft_Bias
        # Format: <command_name> <priority_index> <argument_name>
        m_arg_def = re.match(r'^([A-Za-z0-9_]+)\s+(\d+)\s+([A-Za-z0-9_]+)\s*$', clean)
        if m_arg_def:
            cmd_name = m_arg_def.group(1)
            priority_idx = int(m_arg_def.group(2))
            arg_name = m_arg_def.group(3)
            if cmd_name not in cmd_args:
                cmd_args[cmd_name] = {}
            cmd_args[cmd_name][priority_idx] = arg_name
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
            # Try to parse: C CM00001 0x1 0xcf (command with hex values)
            # or: C CM00001 ; comment (simple command with comment)
            # Also try automatic command detection if enabled
            cmd_name = None
            values_part = None
            comment = None
            
            # First try the standard pattern
            m_cmd_with_values = re.match(r'^C\s+([A-Za-z0-9_]+)\s+(.+?)(?:\s*;\s*(.+))?$', line, re.I)
            if m_cmd_with_values:
                cmd_name = m_cmd_with_values.group(1)
                values_part = m_cmd_with_values.group(2).strip()
                comment = (m_cmd_with_values.group(3) or '').strip()
            elif auto_lookup_enabled and command_detection_patterns:
                # Try automatic command detection using patterns from rules
                for pattern_config in command_detection_patterns:
                    pattern = pattern_config.get('pattern')
                    group = pattern_config.get('group', 1)
                    if pattern:
                        try:
                            match = re.search(pattern, line, re.I)
                            if match:
                                cmd_name = match.group(group)
                                # Try to extract values after command
                                rest = line[match.end():].strip()
                                if rest and not rest.startswith(';'):
                                    values_part = rest.split(';')[0].strip()
                                    comment_match = re.search(r';\s*(.+)', rest)
                                    if comment_match:
                                        comment = comment_match.group(1).strip()
                                break
                        except (re.error, IndexError):
                            continue
            
            if cmd_name:
                # Extract hex values (0x1, 0xcf, etc.) or other values
                values = []
                if values_part:
                    values = re.findall(r'(0x[0-9a-fA-F]+|[0-9]+|\S+)', values_part)
                
                # Check if command exists in database (automatic lookup)
                if values and cmd_name in cmd_args:
                    # Map values to arguments by priority index
                    # Smaller index = higher priority = first value
                    arg_assignments = []
                    sorted_indices = sorted(cmd_args[cmd_name].keys())
                    
                    for i, value in enumerate(values):
                        if i < len(sorted_indices):
                            priority_idx = sorted_indices[i]
                            arg_name = cmd_args[cmd_name][priority_idx]
                            arg_assignments.append(f'{arg_name}={value}')
                    
                    # Format output: CM00001 IRU_Scale_Factor=0x1 ; RW_Speed=0xcf
                    if arg_assignments:
                        output = f'{cmd_name} {" ; ".join(arg_assignments)}'
                        if comment:
                            output += f' ; {comment}'
                        send_cmds.append(output)
                    else:
                        # Fallback if no arguments matched
                        send_cmds.append((cmd_name, comment))
                elif auto_lookup_enabled and cmd_name in cmd_args and not values:
                    # Command found in database but no values provided
                    # Use simple format
                    send_cmds.append((cmd_name, comment or ''))
                else:
                    # Simple command format: C CM00001 ; comment
                    send_cmds.append((cmd_name, comment or ''))
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
            elif isinstance(sc, str):
                # String format (e.g., "CM00001 IRU_Scale_Factor=0x1 ; RW_Speed=0xcf")
                out_lines.append(f'        {sc}')
            else:
                out_lines.append(str(sc))
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
