#!/usr/bin/env python3
"""Fail the build when models.py, types.ts and the engine disagree.

The three are hand-synchronized and nothing generates one from another, so a
field added on one side alone is invisible until it reaches a user.

Compares field names and enum values, not types: `datetime` is `string` over the
wire and every optional spelling differs, so types would be noise.

Run: just model-drift
"""

import enum
import importlib.util
import re
import sys
import types
import typing
from pathlib import Path

import msgspec
import tree_sitter
import tree_sitter_rust

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "backend" / "src" / "models.py"
TYPES = ROOT / "frontend" / "src" / "lib" / "types.ts"
ENGINE = ROOT / "engine" / "src"
MODEL_RS = ENGINE / "model.rs"

# name -> why it has no counterpart. Anything not listed must exist on both
# sides; a new unpaired name fails here rather than drifting unnoticed.
PY_ONLY = {
    "AuthMethod": "credentials, never projected to a client",
    "OAuthAuthorizationCode": "server-side OAuth storage",
    "OAuthClient": "server-side OAuth storage",
    "OAuthConsent": "server-side OAuth storage",
    "OAuthToken": "server-side OAuth storage",
    "TournamentConfig": "a base flattened into the Tournament interface",
    "TournamentMinimal": "a base flattened into the Tournament interface",
    "AuthMethodType": "credentials, never projected to a client",
    "OAuthScope": "server-side OAuth storage",
    "ObjectType": "store and stream tags; sync.ts keys SPECS by literal",
}
TS_ONLY = {
    "City": "geography, sourced from the engine rather than stored",
    "Continent": "geography, sourced from the engine rather than stored",
    "Country": "geography, sourced from the engine rather than stored",
    "Deck": "the engine's deck payload, not the stored DeckObject",
    "LinkMedia": "display-side classification of a community link",
    "LinkPlacement": "display-side classification of a community link",
    "OfflinePlayer": "an offline bundle's player, never stored server-side",
    "VtesCard": "the card catalog, sourced from the engine rather than stored",
}


# Engine modules with no stored model behind them. Anything else in model.rs must
# name a struct in models.py; a new unpaired module fails here.
ENGINE_UNCHECKED = {
    "arg": "keys on argument envelopes the caller builds for one call",
    "standing_row": "the display projection compute_final_standings stamps",
}


def python_side() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    spec = importlib.util.spec_from_file_location("_models", MODELS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    structs, enums = {}, {}
    for name in dir(module):
        obj = getattr(module, name)
        if not isinstance(obj, type):
            continue
        if issubclass(obj, msgspec.Struct):
            structs[name] = {f.encode_name for f in msgspec.structs.fields(obj)}
        elif issubclass(obj, enum.Enum) and obj.__module__ == "_models":
            enums[name] = {e.value for e in obj}
    return structs, enums


# Top-level members only: a nested object literal indents past two spaces, and
# the flattening below mirrors msgspec, which resolves inheritance for us.
_INTERFACE = re.compile(r"^export interface (\w+)(?: extends (\w+))?\s*\{$", re.M)
_MEMBER = re.compile(r"^ {2}(\w+)\??\s*:", re.M)
_ALIAS = re.compile(r"^export type (\w+) =((?:[^;])*);", re.M)


def typescript_side() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    text = TYPES.read_text()
    own, bases = {}, {}
    for match in _INTERFACE.finditer(text):
        end = text.index("\n}", match.end())
        own[match.group(1)] = set(_MEMBER.findall(text[match.end() : end]))
        bases[match.group(1)] = match.group(2)

    def flattened(name: str) -> set[str]:
        base = bases.get(name)
        return own[name] | (flattened(base) if base and base in own else set())

    interfaces = {name: flattened(name) for name in own}
    unions = {}
    for match in _ALIAS.finditer(text):
        values = re.findall(r'"([^"]*)"', match.group(2))
        if values:
            unions[match.group(1)] = set(values)
    return interfaces, unions


def compare(kind: str, py: dict[str, set[str]], ts: dict[str, set[str]]) -> list[str]:
    problems = []
    for name in sorted(set(py) - set(ts) - set(PY_ONLY)):
        problems.append(f"{name}: a {kind} in models.py, absent from types.ts")
    for name in sorted(set(ts) - set(py) - set(TS_ONLY)):
        problems.append(f"{name}: a {kind} in types.ts, absent from models.py")
    for name in sorted(set(py) & set(ts)):
        sides = (("types.ts", py[name] - ts[name]), ("models.py", ts[name] - py[name]))
        for side, missing in sides:
            if missing:
                problems.append(f"{name}: {sorted(missing)} missing from {side}")
    return problems


_BARE_WORD = re.compile(r"[a-z_][a-z0-9_]*")
_COMPARISON = ("==", "!=")
_PATH_REF = re.compile(r"\b([a-z_]+)::([A-Z][A-Z_0-9]*)\b")
_MODULE = re.compile(r"^pub mod (\w+) \{$", re.M)
_CONST = re.compile(r'^    pub const (\w+): &str = "([^"]*)";$', re.M)


def _pascal(module: str) -> str:
    return "".join(part.title() for part in module.split("_"))


def model_rs() -> dict[str, dict[str, str]]:
    text = MODEL_RS.read_text()
    modules = {}
    for match in _MODULE.finditer(text):
        end = text.index("\n}", match.end())
        modules[match.group(1)] = dict(_CONST.findall(text[match.end() : end]))
    return modules


def _parser() -> tuple[tree_sitter.Parser, object]:
    language = tree_sitter.Language(tree_sitter_rust.language())
    return tree_sitter.Parser(language), language


def _text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode()


def _in_test_module(node, source: bytes) -> bool:
    while node is not None:
        if node.type == "mod_item":
            name = node.child_by_field_name("name")
            if name is not None and source[name.start_byte : name.end_byte] == b"tests":
                return True
        node = node.parent
    return False


def _in_object_macro(node, source: bytes) -> bool:
    while node is not None:
        if node.type == "macro_invocation":
            return "object" in _text(node.children[0], source)
        node = node.parent
    return False


def _raw_key_ident(node, source: bytes) -> str | None:
    """`json::object!{ state: v }` names a field with no quotes at all. Matched on
    the token text, not the node type: a key spelled `type` parses as a keyword."""
    if node.child_count or not _BARE_WORD.fullmatch(_text(node, source)):
        return None
    after = node.next_sibling
    if after is None or _text(after, source) != ":":
        return None
    if node.parent is None or node.parent.type != "token_tree":
        return None
    return "an object-literal key" if _in_object_macro(node, source) else None


def _raw_literal(node, source: bytes) -> str | None:
    """What makes this literal a stored key, or None. Covers the shapes a plain
    index sweep misses: macro bodies are token trees, `has_key` is a call."""
    prev, after = node.prev_sibling, node.next_sibling
    before = _text(prev, source) if prev is not None else ""
    follows = _text(after, source) if after is not None else ""
    if before == "[" and follows == "]":
        return "indexed by literal"
    if follows == "=>":
        return "an object-literal key"
    if before == "(" and node.parent is not None and node.parent.type == "arguments":
        call = node.parent.parent
        function = call.child_by_field_name("function") if call is not None else None
        if function is not None:
            if _text(function, source).split(".")[-1] in ("has_key", "remove"):
                return "a has_key/remove key"
    return None


def _macro_pairs(node, source: bytes) -> list[tuple[str, str]]:
    """(field, literal) inside a macro body — `matches!` arms and object values."""
    body = _text(node, source)
    paths = _PATH_REF.findall(body)
    if not paths:
        return []
    pairs = []
    for match in re.finditer(r'"([^"]*)"', body):
        head = body[: match.start()]
        # `unwrap_or("")` supplies a default, not a value the field can hold
        if head.rstrip().endswith("unwrap_or("):
            continue
        if head.rstrip().endswith("=>"):
            keyed = _PATH_REF.findall(head)
            if keyed:
                pairs.append(("::".join(keyed[-1]), match.group(1)))
        elif len(set(paths)) == 1:
            pairs.append(("::".join(paths[0]), match.group(1)))
    return pairs


def _index_loop_keys(node, source: bytes, file, const_arrays: dict) -> list[str]:
    """`for field in [...] { t[field] }` — the list holds field names, wherever
    the list lives. Nothing else distinguishes them from a list of values."""
    pattern = node.child_by_field_name("pattern")
    value = node.child_by_field_name("value")
    body = node.child_by_field_name("body")
    if pattern is None or value is None or body is None:
        return []
    name = _text(pattern, source)
    text = _text(body, source)
    if f"[{name}]" not in text and f"has_key({name})" not in text:
        return []
    source_node = value
    if value.type == "identifier":
        source_node = const_arrays.get(_text(value, source))
        if source_node is None:
            return []
    found = []
    stack = [source_node]
    while stack:
        item = stack.pop()
        stack.extend(item.children)
        if item.type == "string_literal":
            where = f"{file}:{item.start_point[0] + 1}"
            found.append(f"{where}: {_text(item, source)} is a field name in a list")
    return found


def _validate_enum_pairs(node, source: bytes, where: str) -> list[tuple[str, str, str]]:
    """`validate_enum(v, &["A", "B"], tournament_config::FORMAT)` — the list is
    that field's allowed values, so the enum behind the field must hold them."""
    function = node.child_by_field_name("function")
    if function is None or _text(function, source) != "validate_enum":
        return []
    body = _text(node, source)
    field = _PATH_REF.findall(body)
    if not field:
        return []
    values = re.findall(r'"([^"]*)"', body)
    return [(where, "::".join(field[-1]), value) for value in values]


def engine_sites() -> tuple[list[str], list[tuple[str, str, str]]]:
    """Raw stored-key literals, and every `field == "literal"` pairing."""
    parser, _ = _parser()
    raw, compared = [], []
    for file in sorted(ENGINE.rglob("*.rs")):
        if file == MODEL_RS or "tests" in file.name:
            continue
        source = file.read_bytes()
        root = parser.parse(source).root_node
        const_arrays = {}
        stack = [root]
        while stack:
            node = stack.pop()
            stack.extend(node.children)
            if node.type == "const_item":
                name = node.child_by_field_name("name")
                value = node.child_by_field_name("value")
                if name is not None and value is not None:
                    const_arrays[_text(name, source)] = value
        stack = [root]
        while stack:
            node = stack.pop()
            stack.extend(node.children)
            if _in_test_module(node, source):
                continue
            where = f"{file.relative_to(ROOT)}:{node.start_point[0] + 1}"
            if node.type == "for_expression":
                raw += _index_loop_keys(
                    node, source, file.relative_to(ROOT), const_arrays
                )
            if node.type == "string_literal" or not node.child_count:
                if node.type == "string_literal":
                    shape = _raw_literal(node, source)
                else:
                    shape = _raw_key_ident(node, source)
                if shape:
                    raw.append(f"{where}: {_text(node, source)} is {shape}")
                continue
            if node.type == "call_expression":
                compared += _validate_enum_pairs(node, source, where)
            if node.type == "macro_invocation":
                compared += [(where, f, lit) for f, lit in _macro_pairs(node, source)]
                continue
            subject = literal = None
            is_compare = node.type == "binary_expression"
            if is_compare and _text(node.children[1], source) in _COMPARISON:
                left = _text(node.children[0], source)
                right = _text(node.children[2], source)
                for one, other in ((left, right), (right, left)):
                    if _PATH_REF.search(one):
                        found = re.search(r'"([^"]+)"', other)
                        if found:
                            subject, literal = one, found.group(1)
            elif node.type == "assignment_expression":
                left = _text(node.children[0], source)
                right = _text(node.children[2], source).strip()
                found = re.match(r'^"([^"]+)"\s*\.into\(\)$', right)
                if _PATH_REF.search(left) and found:
                    subject, literal = left, found.group(1)
            if subject is None:
                continue
            module, const = _PATH_REF.findall(subject)[-1]
            compared.append((where, f"{module}::{const}", literal))
    return raw, compared


def engine_problems(
    structs: dict[str, set[str]], enums: dict[str, set[str]]
) -> list[str]:
    problems = []
    modules = model_rs()
    for module, consts in sorted(modules.items()):
        # The spelling rule holds everywhere; only the field check needs a model.
        for name, value in sorted(consts.items()):
            if name != value.upper():
                problems.append(
                    f"{module}::{name}: names {value!r}, spell it {value.upper()}"
                )
        if module in ENGINE_UNCHECKED:
            continue
        model = _pascal(module)
        if model not in structs:
            problems.append(f"`{module}`: no {model} in models.py")
            continue
        for name, value in sorted(consts.items()):
            if value not in structs[model]:
                problems.append(f"{module}::{name}: {model} has no field {value!r}")
    for module in sorted(ENGINE_UNCHECKED):
        if module not in modules:
            problems.append(f"`{module}`: listed model-less, absent from model.rs")

    raw, compared = engine_sites()
    problems += raw

    # A literal compared against a field is that field's enum value; the field
    # type says which enum, so a renamed value fails without naming it twice.
    field_enum = {}
    spec = importlib.util.spec_from_file_location("_models_enum", MODELS)
    module_py = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module_py)
    for name in dir(module_py):
        obj = getattr(module_py, name)
        if not (isinstance(obj, type) and issubclass(obj, msgspec.Struct)):
            continue
        for field in msgspec.structs.fields(obj):
            kind = _unwrap(field.type)
            if isinstance(kind, type) and issubclass(kind, enum.Enum):
                module = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
                key = (module, field.encode_name.upper())
                field_enum[key] = kind.__name__
    for where, field, literal in compared:
        module, const = field.split("::")
        name = field_enum.get((module, const))
        if name and literal not in enums.get(name, set()):
            problems.append(f"{where}: {literal!r} is not a {name} value")
    return problems


def _unwrap(kind):
    while hasattr(kind, "__metadata__"):
        kind = kind.__origin__
    origin = typing.get_origin(kind)
    if origin in (list, set, tuple, dict):
        args = typing.get_args(kind)
        return _unwrap(args[-1]) if args else kind
    if origin is typing.Union or origin is types.UnionType:
        for arg in typing.get_args(kind):
            if arg is not type(None):
                return _unwrap(arg)
    return kind


def main() -> int:
    py_structs, py_enums = python_side()
    ts_interfaces, ts_unions = typescript_side()

    problems = []
    for name in sorted(PY_ONLY):
        if name not in py_structs and name not in py_enums:
            problems.append(f"{name}: listed backend-only, absent from models.py")
    for name in sorted(TS_ONLY):
        if name not in ts_interfaces and name not in ts_unions:
            problems.append(f"{name}: listed frontend-only, absent from types.ts")
    problems += compare("struct", py_structs, ts_interfaces)
    problems += compare("enum", py_enums, ts_unions)
    problems += engine_problems(py_structs, py_enums)

    if not problems:
        return 0
    print("the model definitions disagree:\n")
    for problem in problems:
        print(f"  {problem}")
    print(
        "\nThe three are hand-synchronized (wiki/sync.md). Mirror the change, or — if the\n"
        f"shape genuinely belongs to one side — add it to PY_ONLY, TS_ONLY or\n"
        f"ENGINE_UNCHECKED in {Path(__file__).relative_to(ROOT)} with the reason."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
