import logging
import json
import jsonschema
import codecs

from pkg_resources import resource_stream

logger = logging.getLogger(__name__)


class ValidationException(Exception):
    pass


def load_schema(schema_path, package='operator_manifest'):
    """
    :param schema_path: string, file path to the JSON schema
    """
    # Read schema from file
    try:
        resource = resource_stream(package, schema_path)
        schema = codecs.getreader('utf-8')(resource)
    except ImportError:
        logger.error('Unable to find package %s', package)
        raise
    except (IOError, TypeError, FileNotFoundError):
        logger.error('unable to extract JSON schema, cannot validate')
        raise

    # Load schema into Dict
    try:
        schema = json.load(schema)
    except ValueError:
        logger.error('unable to decode JSON schema, cannot validate')
        raise
    return schema


def validate_with_schema(data, schema_path):
    """
    :param data: dict, data to be validated
    :param schema_path: string, file path to the JSON schema
    """
    schema = load_schema(schema_path)
    validator = jsonschema.Draft4Validator(schema=schema)
    try:
        jsonschema.Draft4Validator.check_schema(schema)
        validator.validate(data)
    except jsonschema.SchemaError:
        logger.error('invalid schema, cannot validate')
        raise
    except jsonschema.ValidationError as exc:
        logger.debug("schema validation error: %s", exc)
        exc_message = get_error_message(exc)
        for error in validator.iter_errors(data):
            error_message = get_error_message(error)
            logger.debug("validation error: %s", error_message)
        raise ValidationException(exc_message)


def get_error_message(error):
    path = "".join(
        ('[{}]' if isinstance(element, int) else '.{}').format(element)
        for element in error.path
    )

    # receive all context messages without duplicates caused by the validator 'anyOf'
    error_contexts = set()
    for context in error.context:
        error_contexts.add(context.message)

    error_message = "{}: validating '{}' has failed ({})".format(
                    path or 'at top level', error.validator,
                    ", ".join(error_contexts) or error.message)

    return error_message
