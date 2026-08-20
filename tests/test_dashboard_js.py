"""Static guard against the class of bug that halted client init.

`init()` called `this.attachLibraryTabs()`, which no page defines — the
TypeError stopped every later render, so pages sat on their Figma placeholder
markup.  Any `this.foo()` call must now either resolve to a defined method or
be guarded with a truthiness check.
"""

import re
from pathlib import Path

JS = Path(__file__).resolve().parent.parent / "static" / "js" / "dashboard.js"


def test_every_self_call_is_defined_or_guarded():
    source = JS.read_text(encoding="utf-8")
    defined = set(re.findall(r"^\s{4}(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{", source, re.M))
    defined |= set(re.findall(r"^\s{4}(\w+)\s*:\s*(?:async\s+)?(?:function|\()", source, re.M))
    guarded = set(re.findall(r"if\s*\(\s*(?:this|App)\.(\w+)\s*\)", source))

    called = set(re.findall(r"this\.(\w+)\s*\(", source))
    missing = sorted(called - defined - guarded)
    assert not missing, f"dashboard.js calls undefined, unguarded methods: {missing}"
