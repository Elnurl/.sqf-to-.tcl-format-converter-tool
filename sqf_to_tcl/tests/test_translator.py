import textwrap
from sqf_to_tcl.converter.translator import convert_sqf_string_to_tcl


def test_assignment_and_comment():
    src = """
// comment
_val = 10;
"""
    out = convert_sqf_string_to_tcl(src)
    assert '# comment' in out
    assert 'set val 10' in out


def test_if_and_hint_and_sleep():
    src = textwrap.dedent('''
    _value = 5;
    if (_value > 3) then {
        hint "Value is high";
    };
    sleep 1;
    ''')
    out = convert_sqf_string_to_tcl(src)
    assert 'set value 5' in out
    assert 'if {$value > 3} {' in out
    assert 'puts "Value is high"' in out
    assert 'after 1000' in out


def test_for_loop_format():
    src = textwrap.dedent('''
    for "_i" from 0 to 3 do {
        hint format ["Index: %1", _i];
    };
    ''')
    out = convert_sqf_string_to_tcl(src)
    # basic sanity checks
    assert 'for {set i 0} {$i <= 3} {incr i} {' in out
    assert 'Index: $i' in out or 'puts "Index: $i"' in out
