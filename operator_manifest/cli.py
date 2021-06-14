# SPDX-License-Identifier: BSD-3-Clause
import argparse
import json
import logging
import os.path
import sys

from operator_manifest.operator import ImageName, OperatorManifest
from operator_manifest.resolver import resolve_image_reference


logger = logging.getLogger(__name__)


DEFAULT_OUTPUT_EXTRACT = 'references.json'
DEFAULT_OUTPUT_REPLACE = 'replacements.json'

CLI_LOGGER_FORMAT = '%(message)s'


def main(args=None):
    logging.basicConfig(level=logging.INFO, format=CLI_LOGGER_FORMAT)

    parser = _make_parser()
    namespace = parser.parse_args(args)
    if namespace.command == 'extract':
        extract_image_references(namespace.manifest_dir, output=namespace.output)
    elif namespace.command == 'replace':
        replace_image_references(
            namespace.manifest_dir, namespace.replacements_file, dry_run=namespace.dry_run
        )
    elif namespace.command == 'pin':
        # pin_image_references requires that the output_replace parameter is a seekable file and
        # will raise an error otherwise. In order to provide a more meaningful error to the user,
        # we explicitly check for stdout since that's likely the only case where a non-seekable
        # file is used from the CLI.
        if namespace.output_replace.fileno() == sys.stdout.fileno():
            raise ValueError('Cannot use stdout for --output-replace parameter')
        pin_image_references(
            namespace.manifest_dir,
            authfile=namespace.authfile,
            output_extract=namespace.output_extract,
            output_replace=namespace.output_replace,
            dry_run=namespace.dry_run,
        )
    else:
        parser.error('Insufficient parameters! See usage above')


def _make_parser():
    parser = argparse.ArgumentParser(description='Process operator manifest files')
    subparsers = parser.add_subparsers(dest='command')

    extract_parser = subparsers.add_parser(
        'extract',
        description='Identify all the image references in the CSVs found in MANIFEST_DIR.',
    )
    extract_parser.add_argument(
        'manifest_dir',
        metavar='MANIFEST_DIR',
        help='The path to the directory containing the manifest files.',
    )
    extract_parser.add_argument(
        '--output',
        metavar='OUTPUT',
        default='-',
        type=argparse.FileType('w'),
        help=(
            'The path to store the extracted image references. Use - to specify stdout.'
            ' By default - is used.'
        ),
    )

    replace_parser = subparsers.add_parser(
        'replace',
        description=(
            'Modify the image references in the CSVs found in the MANIFEST_DIR based on the given'
            ' REPLACEMENTS_FILE.'
        ),
    )
    replace_parser.add_argument(
        'manifest_dir',
        metavar='MANIFEST_DIR',
        help='The path to the directory containing the manifest files.',
    )
    replace_parser.add_argument(
        'replacements_file',
        metavar='REPLACEMENTS_FILE',
        type=argparse.FileType('r'),
        help=(
            'The path to the replacements file. The format of this file is a simple JSON object'
            ' where each attribute is a string representing the original image reference and the'
            ' value is a string representing the new value for the image reference. Use - to'
            ' specify stdin.'
        ),
    )
    replace_parser.add_argument(
        '--dry-run',
        default=False,
        action='store_true',
        help=(
            'When set, replacements are not performed. This is useful to determine if the CSV is'
            ' in a state that accepts replacements. By default this option is not set.'
        ),
    )

    pin_parser = subparsers.add_parser(
        'pin',
        description=(
            'Pins to digest all the image references from the CSVs found in MANIFEST_DIR. For'
            ' each image reference, if a tag is used, it is resolved to a digest by querying the'
            ' container image registry. Then, replaces all the image references in the CSVs with'
            ' the resolved, pinned, version.'
        ),
    )
    pin_parser.add_argument(
        'manifest_dir',
        metavar='MANIFEST_DIR',
        help='The path to the directory containing the manifest files.',
    )
    pin_parser.add_argument(
        '--dry-run',
        default=False,
        action='store_true',
        help=('When set, replacements are not performed. By default this option is not set.'),
    )
    pin_parser.add_argument(
        '--output-extract',
        metavar='OUTPUT_EXTRACT',
        default=DEFAULT_OUTPUT_EXTRACT,
        type=argparse.FileType('w+'),
        help=(
            'The path to store the extracted image references from the CSVs.'
            f' By default {DEFAULT_OUTPUT_EXTRACT} is used.'
        ),
    )
    pin_parser.add_argument(
        '--output-replace',
        metavar='OUTPUT_REPLACE',
        default=DEFAULT_OUTPUT_REPLACE,
        type=argparse.FileType('w+'),
        help=(
            'The path to store the extracted image reference replacements from the CSVs.'
            f' By default {DEFAULT_OUTPUT_REPLACE} is used.'
        ),
    )
    pin_parser.add_argument(
        '--authfile',
        metavar='AUTHFILE',
        help='The path to the authentication file for registry communication.',
    )

    return parser


def extract_image_references(manifest_dir, output):
    """
    Identify all the image references from the CSVs found in manifest_dir.

    :param str manifest_dir: the path to the directory where the manifest files are stored
    :param file output: the file-like object to store the extracted image references
    :return: the list of image references extracted from the CSVs
    :rtype: list<str>
    :raises ValueError: if more than one CSV in manifest_dir
    """
    abs_manifest_dir = _normalize_dir_path(manifest_dir)
    logger.info('Extracting image references from %s', abs_manifest_dir)

    operator_manifest = OperatorManifest.from_directory(abs_manifest_dir)
    image_references = [str(pullspec) for pullspec in operator_manifest.csv.get_pullspecs()]

    json.dump(image_references, output)

    return image_references


def replace_image_references(manifest_dir, replacements_file, dry_run=False):
    """
    Use replacements_file to modify the image references in the CSVs found in the manifest_dir.

    :param str manifest_dir: the path to the directory where the manifest files are stored
    :param file replacements_file: the file-like object to the replacements file. The format of
        this file is a simple JSON object where each attribute is a string representing the
        original image reference and the value is a string representing the new value for the
        image reference
    :param bool dry_run: whether or not to apply the replacements
    :raises ValueError: if more than one CSV in manifest_dir
    :raises ValueError: if validation fails
    """
    abs_manifest_dir = _normalize_dir_path(manifest_dir)
    logger.info('Replacing image references in CSV')

    operator_manifest = OperatorManifest.from_directory(abs_manifest_dir)

    if not _should_apply_replacements(manifest_dir):
        logger.warning('Skipping replacements')
        return

    replacements = {}
    for k, v in json.load(replacements_file).items():
        replacements[ImageName.parse(k)] = ImageName.parse(v)
        logger.info('%s -> %s', k, v)

    operator_manifest.csv.replace_pullspecs_everywhere(replacements)

    logger.info('Setting related images section')
    operator_manifest.csv.set_related_images()

    if not dry_run:
        operator_manifest.csv.dump()
        logger.info('Image references replaced')


def pin_image_references(
    manifest_dir,
    authfile=None,
    output_extract=None,
    output_replace=None,
    dry_run=False,
):
    """
    Pins to digest all the image references from the CSVs found in manifest_dir.

    For each image reference, if a tag is used, it is resolved to a digest by querying the
    container image registry. Then, each reference is replaced with the resolved, pinned, version.

    :param str manifest_dir: the path to the directory where the manifest files are stored
    :param str authfile: the path to the authentication file for registry communication
    :param file output_extract: the file-like object to store the extracted image references
    :param file output_replace: the file-like object to store the image reference replacements
    :param bool dry_run: whether or not to apply the replacements
    :raises ValueError: if more than one CSV in manifest_dir
    :raises ValueError: if validation fails
    """
    if not output_replace.seekable():
        raise ValueError('output_replace must be a seekable object')

    references = extract_image_references(manifest_dir, output=output_extract)

    if not _should_apply_replacements(manifest_dir):
        logger.warning('Skipping replacements. Replacement file is not created')
        return

    replacements = {}
    for reference in references:
        # Skip pinning of image references that already use digest
        if '@' in reference:
            continue
        replacements[reference] = resolve_image_reference(reference, authfile=authfile)

    json.dump(replacements, output_replace)
    output_replace.flush()
    output_replace.seek(0)

    replace_image_references(manifest_dir, output_replace, dry_run=dry_run)


def _should_apply_replacements(manifest_dir):
    abs_manifest_dir = _normalize_dir_path(manifest_dir)

    operator_manifest = OperatorManifest.from_directory(abs_manifest_dir)

    if operator_manifest.csv.has_related_images():
        csv_file_name = os.path.basename(operator_manifest.csv.path)
        if operator_manifest.csv.has_related_image_envs():
            raise ValueError(
                f'The ClusterServiceVersion file {csv_file_name} has entries in '
                'spec.relatedImages and one or more containers have RELATED_IMAGE_* '
                'environment variables set. This is not allowed.'
            )
        return False
    return True


def _normalize_dir_path(path):
    abs_path = _normalize_path(path)
    if not os.path.isdir(abs_path):
        raise ValueError(f'{path} is not a directory or does not exist')
    return abs_path


def _normalize_path(path):
    return os.path.abspath(os.path.expanduser(path))


if __name__ == '__main__':
    main()
