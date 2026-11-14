from __future__ import annotations

import pytest
from conftest import fixture_brief, fixture_spec, widget
from jsonschema import Draft202012Validator

from core import schema


@pytest.mark.parametrize("kind", schema.KINDS)
def test_schema_files_are_valid_draft_2020_12(kind):
    Draft202012Validator.check_schema(schema.schema(kind))


def test_fixture_brief_and_spec_pass():
    assert schema.errors("brief", fixture_brief()) == []
    assert schema.errors("spec", fixture_spec()) == []


@pytest.mark.parametrize("mutate, where", [
    (lambda s: widget(s, "UltBlockedText")["font"].update(color="red"), "font/color"),
    (lambda s: widget(s, "UltGauge").update(colour="#FFFFFF"), "widgets/2"),
    (lambda s: widget(s, "UltBlockedText")["slot"].update(padding=[0, 0, 0, 0]), "slot"),
    (lambda s: widget(s, "ChainTimerText")["text"].pop("data"), "text"),
    (lambda s: widget(s, "ChainTimerText")["binding"].update(format="0.00x"), "binding/format"),
    (lambda s: widget(s, "UltArea").update(type="ScrollBox"), "type"),
    (lambda s: s["assets"][0].update(provenance="midjourney"), "assets/0/provenance"),
])
def test_spec_schema_rejects(mutate, where):
    s = fixture_spec()
    mutate(s)
    errs = schema.errors("spec", s)
    assert errs, "schema accepted a broken spec"
    assert any(where.split("/")[0] in e for e in errs), errs


def test_patch_schema():
    ok = {"schema_version": 1, "source": "fix", "ops": [{"op": "set", "widget": "UltGauge", "path": "slot.position", "value": [0, -72]}]}
    assert schema.errors("patch", ok) == []
    missing_value = {"schema_version": 1, "source": "fix", "ops": [{"op": "set", "widget": "UltGauge", "path": "slot.position"}]}
    assert schema.errors("patch", missing_value)
    bad_path = {"schema_version": 1, "source": "fix", "ops": [{"op": "set", "widget": "UltGauge", "path": "Slot/Position", "value": 1}]}
    assert schema.errors("patch", bad_path)
    add = {"schema_version": 1, "source": "fault", "ops": [{"op": "add_widget", "widget": {"id": "X", "type": "Spacer", "parent": "Root"}}]}
    assert schema.errors("patch", add) == []
    add_bad = {"schema_version": 1, "source": "fault", "ops": [{"op": "add_widget", "widget": {"id": "X", "type": "Nope"}}]}
    assert schema.errors("patch", add_bad)


def test_require_raises_with_errors():
    with pytest.raises(schema.SchemaError) as e:
        schema.require("report", {"schema_version": 1})
    assert e.value.kind == "report" and e.value.errors
