"""JSON Schema 검사 — schemas/*.schema.json (Draft 2020-12). 스키마끼리 urn:uigen:<kind> 로 참조한다."""
from __future__ import annotations

import functools
import json

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from core.config import UIGEN_DIR

SCHEMA_DIR = UIGEN_DIR / "schemas"
KINDS = ("spec", "patch", "brief", "manifest", "report", "fixes", "codegen", "build", "lineage")


class SchemaError(ValueError):
    def __init__(self, kind: str, errors: list[str]):
        self.kind = kind
        self.errors = errors
        super().__init__(f"{kind} schema: {len(errors)} error(s): " + "; ".join(errors[:5]))


@functools.lru_cache(maxsize=1)
def _load() -> tuple[Registry, dict[str, dict]]:
    schemas = {k: json.loads((SCHEMA_DIR / f"{k}.schema.json").read_text(encoding="utf-8")) for k in KINDS}
    registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas.values())
    return registry, schemas


def schema(kind: str) -> dict:
    return _load()[1][kind]


def validator(kind: str) -> Draft202012Validator:
    registry, schemas = _load()
    return Draft202012Validator(schemas[kind], registry=registry)


def errors(kind: str, obj) -> list[str]:
    out = []
    for e in sorted(validator(kind).iter_errors(obj), key=lambda e: list(map(str, e.absolute_path))):
        where = "/".join(str(p) for p in e.absolute_path) or "<root>"
        out.append(f"{where}: {e.message}")
    return out


def require(kind: str, obj) -> None:
    errs = errors(kind, obj)
    if errs:
        raise SchemaError(kind, errs)
