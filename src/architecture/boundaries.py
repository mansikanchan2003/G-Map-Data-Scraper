"""
Checks the code against the module map (src.architecture.modules).

Reads every import in src/ (with ast, without running anything), works out which
module each file and each imported file belongs to, and lists the reaches across
modules: a business module importing another business module's file, or an
integration importing a business module. Imports of platform and integrations are
always fine.

    python -m src.architecture.boundaries            # the report
    python -m src.architecture.boundaries --update   # write today's reaches as the baseline

The test suite fails on a reach that is not in the baseline (baseline.json), so the
count can only go down. When a reach is removed, run --update to shrink the baseline.
"""
import ast
import json
import os
import sys
from collections import Counter
from typing import Dict, List, Optional, Set, Tuple

from src.architecture.modules import MODULES, SHARED

SRC = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
BASELINE = os.path.join(os.path.dirname(__file__), "baseline.json")
# The composition root: these put the modules together (the app, its threads, the
# worker entrypoint, the model registry), so they import everything by design. The golden
# set (evals/) drives the whole app as a test would, and is skipped the same way.
COMPOSITION = {"main", "background", "worker", "models/__init__"}


def _files() -> List[str]:
    """Every Python file under src/, as "services/inbox" (no .py)."""
    out = []
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith(".py"):
                rel = os.path.relpath(os.path.join(root, f), SRC).replace(os.sep, "/")[:-3]
                out.append(rel[: -len("/__init__")] + "/__init__" if rel.endswith("/__init__") else rel)
    return sorted(out)


def module_of(path: str) -> Optional[str]:
    for module, entries in MODULES.items():
        for e in entries:
            if (e.endswith("/") and path.startswith(e)) or path == e:
                return module
    return None


def unassigned() -> List[str]:
    """Files no module claims: each must be given one."""
    return [f for f in _files() if module_of(f) is None and not f.endswith("__init__")]


def _model_files() -> Dict[str, str]:
    """Model class -> the file defining it, from src/models/__init__.py, so that
    "from src.models import WhatsAppConversation" counts as reaching models/inbox."""
    out: Dict[str, str] = {}
    tree = ast.parse(open(os.path.join(SRC, "models", "__init__.py"), encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
            for a in node.names:
                out[a.asname or a.name] = "models/" + node.module
    return out


def _imports(path: str) -> Set[str]:
    """The src/ files a file imports, as paths."""
    full = os.path.join(SRC, path + ".py")
    try:
        tree = ast.parse(open(full, encoding="utf-8").read(), filename=full)
    except SyntaxError:
        return set()
    known = set(_files())
    models = _model_files()
    out: Set[str] = set()

    def add(dotted: str) -> None:
        if not dotted.startswith("src."):
            return
        p = dotted[4:].replace(".", "/")
        if p in known:
            out.add(p)
        elif p + "/__init__" in known:
            out.add(p + "/__init__")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                add(a.name)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if node.module == "src.models":
                for a in node.names:      # a model class: the file that defines it
                    if a.name in models:
                        out.add(models[a.name])
                continue
            add(node.module)
            for a in node.names:          # "from src.services import inbox"
                add(f"{node.module}.{a.name}")
    return out - {path}


def reaches() -> List[Tuple[str, str]]:
    """(importing file, imported file) for every import that crosses modules the map forbids."""
    out = []
    for f in _files():
        mine = module_of(f)
        if mine is None or f in COMPOSITION or f.startswith("evals/"):
            continue
        for target in sorted(_imports(f)):
            theirs = module_of(target)
            if theirs is None or theirs == mine:
                continue
            if theirs in SHARED:
                # Platform and integrations are for everyone.
                continue
            out.append((f, target))
    return out


def forbidden_integration_reaches() -> List[Tuple[str, str]]:
    """An adapter importing a business module: never allowed, baseline or not."""
    return [(f, t) for f, t in reaches() if module_of(f) == "integrations"]


def load_baseline() -> Set[Tuple[str, str]]:
    try:
        return {tuple(x) for x in json.load(open(BASELINE, encoding="utf-8"))["reaches"]}
    except (OSError, ValueError, KeyError):
        return set()


def new_reaches() -> List[Tuple[str, str]]:
    base = load_baseline()
    return [r for r in reaches() if r not in base]


def matrix(pairs: List[Tuple[str, str]]) -> Dict[str, Dict[str, int]]:
    counts = Counter((module_of(f), module_of(t)) for f, t in pairs)
    out: Dict[str, Dict[str, int]] = {}
    for (a, b), n in sorted(counts.items()):
        out.setdefault(a, {})[b] = n
    return out


def main(argv: List[str]) -> int:
    pairs = reaches()
    if "--update" in argv:
        json.dump({"note": "Reaches across modules that existed when the map was drawn (22 Nov 2026). "
                           "Only ever shrink this: python -m src.architecture.boundaries --update",
                   "count": len(pairs), "reaches": [list(p) for p in pairs]},
                  open(BASELINE, "w", encoding="utf-8"), indent=1)
        print(f"baseline written: {len(pairs)} reaches")
        return 0
    print(f"{len(pairs)} reaches across modules (baseline {len(load_baseline())})")
    for a, row in matrix(pairs).items():
        print(f"  {a:13} -> " + ", ".join(f"{b} {n}" for b, n in sorted(row.items(), key=lambda x: -x[1])))
    missing = unassigned()
    if missing:
        print("not in any module:", ", ".join(missing))
    fresh = new_reaches()
    if fresh:
        print("NEW reaches (not in the baseline):")
        for f, t in fresh:
            print(f"  {f} -> {t}")
    return 1 if fresh or missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
