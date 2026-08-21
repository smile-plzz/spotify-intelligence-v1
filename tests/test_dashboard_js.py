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


CLASS_SELECTOR = re.compile(r"""querySelector(?:All)?\(\s*['"]([^'"]+)['"]""")
TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


def _class_names(selector: str) -> set[str]:
    """Class names in one alternative of a selector list."""
    return set(re.findall(r"\.([A-Za-z0-9_-]+)", selector))


def test_every_selector_the_client_queries_exists_in_some_template():
    """Catch selector drift between dashboard.js and the templates.

    A renderer that queries a class no page defines silently does nothing —
    which is how `.lib-albums-grid` and `.diversity-score-value` left the
    Library and Taste pages showing their mock values.
    """
    source = JS.read_text(encoding="utf-8")
    markup = "\n".join(
        p.read_text(encoding="utf-8") for p in TEMPLATES.glob("*.html")
    )
    defined = set(re.findall(r'class="([^"]+)"', markup))
    defined = {cls for group in defined for cls in group.split()}

    unmatched = []
    for selector in CLASS_SELECTOR.findall(source):
        alternatives = [alt for alt in selector.split(",") if "." in alt]
        if not alternatives:
            continue
        # A comma list is a fallback chain: one match is enough.
        if not any(_class_names(alt) <= defined for alt in alternatives):
            unmatched.append(selector.strip())

    assert not unmatched, f"dashboard.js queries selectors no template defines: {sorted(set(unmatched))}"
