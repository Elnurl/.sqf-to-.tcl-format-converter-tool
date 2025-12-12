"""CLI entry point for SQF -> TCL converter."""
from __future__ import annotations
import argparse
from pathlib import Path
from sqf_to_tcl.converter.translator import convert_sqf_string_to_tcl, save_tcl_output


def main():
    p = argparse.ArgumentParser(description='Convert SQF file to TCL')
    p.add_argument('input', help='Path to input .sqf file')
    p.add_argument('output', help='Path to output .tcl file')
    p.add_argument('--debug', action='store_true', help='Enable debug logging')
    p.add_argument('--report', action='store_true', help='Force report-style conversion (company format)')
    p.add_argument('--rules', help='Path to rules.yaml to customize report mappings')
    p.add_argument('--db', help='Path to argument database .txt file (format: command priority_index argument_name)')
    args = p.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f'Input file not found: {input_path}')
        raise SystemExit(2)

    source = input_path.read_text(encoding='utf-8')
    tcl = convert_sqf_string_to_tcl(source, debug=args.debug, report=args.report if args.report else None, rules_path=args.rules, db_path=args.db)
    save_tcl_output(tcl, args.output)
    print(f'Wrote: {args.output}')


if __name__ == '__main__':
    main()
