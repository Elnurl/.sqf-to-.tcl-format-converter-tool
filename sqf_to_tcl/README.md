# SQF → TCL Converter (Python)

Small proof-of-concept tool to convert basic SQF (Arma 3 scripting) constructs to TCL.

Usage

Run the CLI:

```powershell
python main.py examples/example1.sqf examples/output.tcl
```

Features

- Converts variable assignments: `_var = 10;` → `set var 10`
- if/then blocks, for-from-to-do loops, while loops
- hint → puts, sleep → after
- Preserves comments (// → #)
- Unknown constructs are left as `# TODO` comments in output

Project layout

```
sqf_to_tcl/
├── parser/
│   └── sqf_parser.py
├── converter/
│   └── translator.py
├── main.py
├── examples/
└── tests/
```

Notes

This is a pragmatic, regex-driven initial implementation. It's designed to be
modular so a proper parser (Lark/PLY) can be swapped in later.
