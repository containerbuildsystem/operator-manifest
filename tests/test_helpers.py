import pytest
import jsonschema
from flexmock import flexmock

from operator_manifest.helpers import load_schema, validate_with_schema, ValidationException
import operator_manifest.helpers as helpers_module


@pytest.mark.parametrize(('package', 'package_pass'), [
    ('operator_manifest', True),
    ('FOO', False)
])
def test_load_schema_package(package, package_pass, caplog):
    schema_path = 'schemas/csv_schema.json'
    if not package_pass:
        with pytest.raises(ImportError):
            load_schema(schema_path, package)
        assert f"Unable to find package {package}" in caplog.text
    else:
        assert isinstance(load_schema(schema_path, package), dict)


@pytest.mark.parametrize(('schema_path', 'schema_pass'), [
    ('schemas/csv_schema.json', True),
    ('schemas/foo.json', False)
])
def test_load_schema_schema(schema_path, schema_pass, caplog):
    if not schema_pass:
        with pytest.raises(FileNotFoundError):
            load_schema(schema_path)
        assert "unable to extract JSON schema, cannot validate" in caplog.text
    else:
        assert isinstance(load_schema(schema_path), dict)


@pytest.mark.parametrize(
    ("data, validation_pass, expected_err_message"),
    [
        (
            {"kind": "ClusterServiceVersion", "spec": {"install": {}}},
            False,
            "at top level: validating 'required' has failed ('metadata' is a required property)",
        ),
        (
            {
                "kind": "ClusterServiceVersion",
                "metadata": {"name": "foo"},
                "spec": {"install": {}},
            },
            True,
            None,
        ),
    ],
)
def test_validate_with_schema(data, validation_pass, expected_err_message, caplog):
    if not validation_pass:
        with pytest.raises(ValidationException) as exc_info:
            validate_with_schema(data, "schemas/csv_schema.json")
        assert "schema validation error" in caplog.text
        assert expected_err_message in str(exc_info)
    else:
        validate_with_schema(data, "schemas/csv_schema.json")


def test_validate_with_schema_bad_schema(caplog, tmpdir):
    data = {
        "kind": "ClusterServiceVersion",
        "metadata": {"name": "foo"},
        "spec": {"install": {}},
    }
    schema = {
        'type': 'foo',  # Nonexistent type
        'properties': {
            'name': {
                'type': 'string'
            }
        }
    }
    (flexmock(helpers_module)
     .should_receive('load_schema')
     .replace_with(lambda x: schema))
    with pytest.raises(jsonschema.SchemaError):
        validate_with_schema(data, 'foo')
    assert 'invalid schema, cannot validate' in caplog.text
