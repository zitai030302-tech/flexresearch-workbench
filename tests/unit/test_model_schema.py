from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from flexresearch.experiment_tools import AnalyzeExperimentInput
from flexresearch.model_schema import inline_local_refs


def test_scientific_schema_expands_nested_filter_without_relaxing_constraints():
    original = AnalyzeExperimentInput.model_json_schema()
    before = deepcopy(original)
    flat = inline_local_refs(original)
    assert original == before
    assert '"$ref"' not in json.dumps(flat)
    assert '"$defs"' not in json.dumps(flat)
    parameters = flat["properties"]["analysis_parameters"]
    band = parameters["properties"]["filter"]["anyOf"][0]
    assert band["additionalProperties"] is False
    assert band["properties"]["order"]["maximum"] == 10
    assert band["properties"]["low_cut"]["anyOf"][0]["exclusiveMinimum"] == 0
    assert flat["required"] == ["experiment_id"]
    assert flat["properties"]["channel"]["anyOf"] == [{"type": "string"}, {"type": "integer"}, {"type": "null"}]
    with pytest.raises(ValidationError):
        AnalyzeExperimentInput(experiment_id=1, analysis_parameters={"filter": {"low_cut": -1}})


def test_literals_and_property_names_are_not_treated_as_schema_keywords():
    literal = {"$ref": "https://example.invalid/private", "$defs": {"x": "literal"}}
    schema = {"type": "object", "properties": {"$defs": {"type": "string"}, "$ref": {"type": "string"}}, "default": literal, "examples": [literal]}
    assert inline_local_refs(schema) == schema


def test_ref_siblings_are_conjoined_instead_of_overwriting_constraints():
    schema = {"$defs": {"x": {"type": "integer", "minimum": 5}}, "$ref": "#/$defs/x", "minimum": 0, "maximum": 10}
    assert inline_local_refs(schema) == {"allOf": [{"type": "integer", "minimum": 5}, {"minimum": 0, "maximum": 10}]}


def test_escaped_json_pointer_and_repeated_nonrecursive_refs():
    schema = {"$defs": {"a/b~c": {"type": "number"}}, "type": "object", "properties": {name: {"$ref": "#/$defs/a~1b~0c"} for name in ("first", "second")}}
    assert inline_local_refs(schema)["properties"] == {"first": {"type": "number"}, "second": {"type": "number"}}


@pytest.mark.parametrize("schema", [
    {"$ref": "https://example.invalid/schema"},
    {"$ref": "#/$defs/missing"},
    {"$defs": {"x": {"$ref": "#/$defs/x"}}, "$ref": "#/$defs/x"},
    {"$defs": {"x": "not a schema"}, "$ref": "#/$defs/x"},
])
def test_unportable_refs_fail_explicitly(schema):
    with pytest.raises(ValueError):
        inline_local_refs(schema)


def test_every_application_tool_exports_portable_parameters():
    import app
    schemas = app.build_application_tool_registry().openai_schemas()
    assert len(schemas) == 20
    for item in schemas:
        parameters = json.dumps(item["function"]["parameters"])
        assert '"$ref"' not in parameters
        assert '"$defs"' not in parameters

