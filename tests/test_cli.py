# SPDX-License-Identifier: BSD-3-Clause
import io
import json
import pytest
from textwrap import dedent
from unittest import mock

from operator_manifest.cli import (
    extract_image_references,
    main,
    pin_image_references,
    replace_image_references,
    resolve_image_references,
)

CSV_TEMPLATE = """\
apiVersion: operators.coreos.com/v1alpha1
kind: ClusterServiceVersion
spec:
  install:
    spec:
      deployments:
      - spec:
          template:
            spec:
              containers:
              - name: spam-operator
                image: {spam}
              - name: eggs
                image: {eggs}
"""

CSV_TEMPLATE_WITH_RELATED_IMAGES = (
    CSV_TEMPLATE
    + """\
  relatedImages:
  - name: spam-operator
    image: {spam}
  - name: eggs
    image: {eggs}
"""
)

CSV_RESOLVED_TEMPLATE = """\
apiVersion: operators.coreos.com/v1alpha1
kind: ClusterServiceVersion
spec:
  install:
    spec:
      deployments:
      - spec:
          template:
            spec:
              containers:
              - name: spam-operator
                image: {spam}
              - name: eggs
                image: {eggs}
  relatedImages:
  - name: spam-operator
    image: {spam}
  - name: eggs
    image: {eggs}
"""


class TestExtractImageReferences:
    def test_extract_image_references(self, tmp_path):
        eggs_image_reference = 'registry.example.com/eggs:9.8'
        spam_image_reference = 'registry.example.com/maps/spam-operator@sha256:1'

        manifest_dir = tmp_path / 'manifests'
        manifest_dir.mkdir()
        csv_path = manifest_dir / 'spam.yaml'
        csv_path.write_text(
            CSV_TEMPLATE.format(eggs=eggs_image_reference, spam=spam_image_reference)
        )

        output_file = io.StringIO()
        extract_image_references(str(manifest_dir), output=output_file)
        output_file.seek(0)

        assert sorted(json.load(output_file)) == [eggs_image_reference, spam_image_reference]

    @pytest.mark.parametrize('dry_run', (True, False))
    def test_check_manifest_dir_exists(self, tmp_path, dry_run):
        with pytest.raises(ValueError, match=r'/manifests is not a directory or does not exist'):
            extract_image_references(str(tmp_path / 'manifests'), output=io.StringIO())


class TestResolveImageReferences:
    @mock.patch('operator_manifest.cli.resolve_image_reference')
    def test_resolve_all_image_references(self, resolve_image_reference):
        replacements = {
            'registry.example.com/eggs:9.8': 'registry.example.com/eggs@sha256:2',
            'registry.example.com/maps/spam-operator:1.2': (
                'registry.example.com/maps/spam-operator@sha256:1'
            ),
        }
        resolve_image_reference.side_effect = lambda image_ref, authfile: replacements[image_ref]

        images_file = io.StringIO(json.dumps(list(replacements.keys())))
        output_file = io.StringIO()

        resolve_image_references(images_file, output_file)

        output_file.seek(0)
        assert json.load(output_file) == replacements

    @pytest.mark.parametrize('dry_run', (True, False))
    @mock.patch('operator_manifest.cli.resolve_image_reference')
    def test_resolve_some_image_references(self, resolve_image_reference, tmp_path, dry_run):
        replacements = {'registry.example.com/eggs:9.8': 'registry.example.com/eggs@sha256:2'}
        resolve_image_reference.side_effect = lambda image_ref, authfile: replacements[image_ref]

        images_file = io.StringIO(
            json.dumps(
                list(replacements.keys()) + ['registry.example.com/maps/spam-operator@sha256:1']
            )
        )
        output_file = io.StringIO()

        resolve_image_references(images_file, output_file)

        output_file.seek(0)
        assert json.load(output_file) == replacements

    @mock.patch('operator_manifest.cli.resolve_image_reference')
    def test_authfile_is_used(self, resolve_image_reference, tmp_path):
        replacements = {'registry.example.com/eggs:9.8': 'registry.example.com/eggs@sha256:2'}
        resolve_image_reference.side_effect = lambda image_ref, authfile: replacements[image_ref]

        authfile = tmp_path / 'auth.json'

        images_file = io.StringIO(json.dumps(list(replacements.keys())))
        output_file = io.StringIO()

        resolve_image_references(images_file, output_file, authfile=str(authfile))
        resolve_image_reference.assert_called_with(
            list(replacements.keys())[0], authfile=str(authfile)
        )


class TestReplaceImageReferences:
    @pytest.mark.parametrize('dry_run', (True, False))
    def test_full_replacement(self, tmp_path, dry_run):
        eggs_image_reference = 'registry.example.com/eggs:9.8'
        spam_image_reference = 'registry.example.com/maps/spam-operator:1.2'

        eggs_image_reference_resolved = 'registry.example.com/eggs@sha256:2'
        spam_image_reference_resolved = 'registry.example.com/maps/spam-operator@sha256:1'

        manifest_dir = tmp_path / 'manifests'
        manifest_dir.mkdir()
        csv_path = manifest_dir / 'spam.yaml'
        original_csv_text = CSV_TEMPLATE.format(
            eggs=eggs_image_reference, spam=spam_image_reference
        )
        csv_path.write_text(original_csv_text)

        replacements = {
            spam_image_reference: spam_image_reference_resolved,
            eggs_image_reference: eggs_image_reference_resolved,
        }
        replacements_input_file = io.StringIO()
        json.dump(replacements, replacements_input_file)
        replacements_input_file.seek(0)

        replace_image_references(str(manifest_dir), replacements_input_file, dry_run=dry_run)

        if dry_run:
            assert csv_path.read_text() == original_csv_text
        else:
            assert csv_path.read_text() == CSV_RESOLVED_TEMPLATE.format(
                eggs=eggs_image_reference_resolved, spam=spam_image_reference_resolved
            )

    @pytest.mark.parametrize('dry_run', (True, False))
    def test_partial_replacement(self, tmp_path, dry_run):
        eggs_image_reference = 'registry.example.com/eggs:9.8'
        spam_image_reference = 'registry.example.com/maps/spam-operator:1.2'

        eggs_image_reference_resolved = 'registry.example.com/eggs@sha256:2'

        manifest_dir = tmp_path / 'manifests'
        manifest_dir.mkdir()
        csv_path = manifest_dir / 'spam.yaml'
        original_csv_text = CSV_TEMPLATE.format(
            eggs=eggs_image_reference, spam=spam_image_reference
        )
        csv_path.write_text(original_csv_text)

        replacements = {
            eggs_image_reference: eggs_image_reference_resolved,
        }
        replacements_input_file = io.StringIO()
        json.dump(replacements, replacements_input_file)
        replacements_input_file.seek(0)

        replace_image_references(str(manifest_dir), replacements_input_file, dry_run=dry_run)

        if dry_run:
            assert csv_path.read_text() == original_csv_text
        else:
            # spam image reference is not resolved
            assert csv_path.read_text() == CSV_RESOLVED_TEMPLATE.format(
                eggs=eggs_image_reference_resolved, spam=spam_image_reference
            )

    @pytest.mark.parametrize('dry_run', (True, False))
    def test_skip_replacements(self, tmp_path, dry_run):
        eggs_image_reference = 'registry.example.com/eggs:9.8'
        spam_image_reference = 'registry.example.com/maps/spam-operator:1.2'

        eggs_image_reference_resolved = 'registry.example.com/eggs@sha256:2'
        spam_image_reference_resolved = 'registry.example.com/maps/spam-operator@sha256:1'

        manifest_dir = tmp_path / 'manifests'
        manifest_dir.mkdir()
        csv_path = manifest_dir / 'spam.yaml'
        original_csv_text = CSV_TEMPLATE_WITH_RELATED_IMAGES.format(
            eggs=eggs_image_reference, spam=spam_image_reference
        )
        csv_path.write_text(original_csv_text)

        replacements = {
            spam_image_reference: spam_image_reference_resolved,
            eggs_image_reference: eggs_image_reference_resolved,
        }
        replacements_input_file = io.StringIO()
        json.dump(replacements, replacements_input_file)
        replacements_input_file.seek(0)

        replace_image_references(str(manifest_dir), replacements_input_file, dry_run=dry_run)

        # relatedImages section exists, CSV should not be modified
        assert csv_path.read_text() == original_csv_text

    @pytest.mark.parametrize('dry_run', (True, False))
    def test_error_on_related_images_with_related_image_env(self, tmp_path, dry_run):
        eggs_image_reference = 'registry.example.com/eggs:9.8'
        spam_image_reference = 'registry.example.com/maps/spam-operator:1.2'

        manifest_dir = tmp_path / 'manifests'
        manifest_dir.mkdir()
        csv_path = manifest_dir / 'spam.yaml'
        # relatedImages is set and one of the containers uses an environment variable
        # with the suffix RELATED_IMAGE_. This is not allowed.
        original_csv_text = dedent(
            """\
            apiVersion: operators.coreos.com/v1alpha1
            kind: ClusterServiceVersion
            spec:
              install:
                spec:
                  deployments:
                  - spec:
                      template:
                        spec:
                          containers:
                          - name: spam-operator
                            image: {spam}
                            env:
                            - name: RELATED_IMAGE_BACON
                              value: {eggs}
              relatedImages:
              - name: spam-operator
                image: {spam}
              - name: eggs
                image: {eggs}
        """
        ).format(spam=spam_image_reference, eggs=eggs_image_reference)
        csv_path.write_text(original_csv_text)

        replacements_input_file = io.StringIO()
        json.dump({}, replacements_input_file)
        replacements_input_file.seek(0)

        with pytest.raises(ValueError, match=r'This is not allowed'):
            replace_image_references(str(manifest_dir), replacements_input_file, dry_run=dry_run)

        # Verify CSV is left intact after failure
        assert csv_path.read_text() == original_csv_text

    @pytest.mark.parametrize('dry_run', (True, False))
    def test_check_manifest_dir_exists(self, tmp_path, dry_run):
        with pytest.raises(ValueError, match=r'/manifests is not a directory or does not exist'):
            replace_image_references(str(tmp_path / 'manifests'), io.StringIO(), dry_run=dry_run)


class TestPinImageReferences:
    @pytest.mark.parametrize('dry_run', (True, False))
    @mock.patch('operator_manifest.cli.resolve_image_reference')
    def test_full_pinning(self, resolve_image_reference, tmp_path, dry_run):

        eggs_image_reference = 'registry.example.com/eggs:9.8'
        spam_image_reference = 'registry.example.com/maps/spam-operator:1.2'

        eggs_image_reference_resolved = 'registry.example.com/eggs@sha256:2'
        spam_image_reference_resolved = 'registry.example.com/maps/spam-operator@sha256:1'

        replacements = {
            spam_image_reference: spam_image_reference_resolved,
            eggs_image_reference: eggs_image_reference_resolved,
        }
        resolve_image_reference.side_effect = lambda image_ref, authfile: replacements[image_ref]

        manifest_dir = tmp_path / 'manifests'
        manifest_dir.mkdir()
        csv_path = manifest_dir / 'spam.yaml'
        original_csv_text = CSV_TEMPLATE.format(
            eggs=eggs_image_reference, spam=spam_image_reference
        )
        csv_path.write_text(original_csv_text)

        output_extract_file = io.StringIO()
        output_replace_file = io.StringIO()
        pin_image_references(
            str(manifest_dir),
            output_extract=output_extract_file,
            output_replace=output_replace_file,
            dry_run=dry_run,
        )

        if dry_run:
            assert csv_path.read_text() == original_csv_text
        else:
            assert csv_path.read_text() == CSV_RESOLVED_TEMPLATE.format(
                eggs=eggs_image_reference_resolved, spam=spam_image_reference_resolved
            )

        output_extract_file.seek(0)
        assert sorted(json.load(output_extract_file)) == [
            eggs_image_reference,
            spam_image_reference,
        ]

        output_replace_file.seek(0)
        assert (json.load(output_replace_file)) == {
            eggs_image_reference: eggs_image_reference_resolved,
            spam_image_reference: spam_image_reference_resolved,
        }

    @pytest.mark.parametrize('dry_run', (True, False))
    @mock.patch('operator_manifest.cli.resolve_image_reference')
    def test_partial_pinning(self, resolve_image_reference, tmp_path, dry_run):

        eggs_image_reference = 'registry.example.com/eggs:9.8'
        # Spam image is already pinned
        spam_image_reference = 'registry.example.com/maps/spam-operator@sha256:1'

        eggs_image_reference_resolved = 'registry.example.com/eggs@sha256:2'

        replacements = {eggs_image_reference: eggs_image_reference_resolved}
        resolve_image_reference.side_effect = lambda image_ref, authfile: replacements[image_ref]

        manifest_dir = tmp_path / 'manifests'
        manifest_dir.mkdir()
        csv_path = manifest_dir / 'spam.yaml'
        original_csv_text = CSV_TEMPLATE.format(
            eggs=eggs_image_reference, spam=spam_image_reference
        )
        csv_path.write_text(original_csv_text)

        output_extract_file = io.StringIO()
        output_replace_file = io.StringIO()
        pin_image_references(
            str(manifest_dir),
            output_extract=output_extract_file,
            output_replace=output_replace_file,
            dry_run=dry_run,
        )

        if dry_run:
            assert csv_path.read_text() == original_csv_text
        else:
            assert csv_path.read_text() == CSV_RESOLVED_TEMPLATE.format(
                eggs=eggs_image_reference_resolved, spam=spam_image_reference
            )

        output_extract_file.seek(0)
        assert sorted(json.load(output_extract_file)) == [
            eggs_image_reference,
            spam_image_reference,
        ]

        output_replace_file.seek(0)
        # Spam image is not included in replacements because it is already pinned
        assert (json.load(output_replace_file)) == {
            eggs_image_reference: eggs_image_reference_resolved,
        }

    @pytest.mark.parametrize('dry_run', (True, False))
    def test_output_extract_is_seekable(self, tmp_path, dry_run):
        # Ideally, simply use sys.stdout as a non-seekable file object. However, pytest does
        # some special manipulation to sys.stdout that makes it seekable during unit tests.
        output_replace_file = io.IOBase()
        assert not output_replace_file.seekable()
        with pytest.raises(ValueError, match=r'output_replace must be a seekable object'):
            pin_image_references(
                str(tmp_path / 'manifests'),
                output_extract=io.StringIO(),
                output_replace=output_replace_file,
                dry_run=dry_run,
            )

    @pytest.mark.parametrize('dry_run', (True, False))
    def test_output_replace_is_seekable(self, tmp_path, dry_run):
        # Ideally, simply use sys.stdout as a non-seekable file object. However, pytest does
        # some special manipulation to sys.stdout that makes it seekable during unit tests.
        output_extract_file = io.IOBase()
        assert not output_extract_file.seekable()
        with pytest.raises(ValueError, match=r'output_extract must be a seekable object'):
            pin_image_references(
                str(tmp_path / 'manifests'),
                output_extract=output_extract_file,
                output_replace=io.StringIO(),
                dry_run=dry_run,
            )

    @pytest.mark.parametrize('dry_run', (True, False))
    @mock.patch('operator_manifest.cli.resolve_image_reference')
    def test_skip_replacements(self, resolve_image_reference, tmp_path, dry_run):
        eggs_image_reference = 'registry.example.com/eggs:9.8'
        spam_image_reference = 'registry.example.com/maps/spam-operator:1.2'

        manifest_dir = tmp_path / 'manifests'
        manifest_dir.mkdir()
        csv_path = manifest_dir / 'spam.yaml'
        original_csv_text = CSV_TEMPLATE_WITH_RELATED_IMAGES.format(
            eggs=eggs_image_reference, spam=spam_image_reference
        )
        csv_path.write_text(original_csv_text)

        output_extract_file = io.StringIO()
        output_replace_file = io.StringIO()
        pin_image_references(
            str(manifest_dir),
            output_extract=output_extract_file,
            output_replace=output_replace_file,
            dry_run=dry_run,
        )

        resolve_image_reference.assert_not_called()
        assert csv_path.read_text() == original_csv_text

        output_extract_file.seek(0)
        assert sorted(json.load(output_extract_file)) == [
            eggs_image_reference,
            spam_image_reference,
        ]

        output_replace_file.seek(0)
        assert output_replace_file.read() == ''

    @pytest.mark.parametrize('dry_run', (True, False))
    def test_check_manifest_dir_exists(self, tmp_path, dry_run):
        with pytest.raises(ValueError, match=r'/manifests is not a directory or does not exist'):
            pin_image_references(
                str(tmp_path / 'manifests'),
                output_extract=io.StringIO(),
                output_replace=io.StringIO(),
                dry_run=dry_run,
            )


class TestArgumentParsing:
    @mock.patch('operator_manifest.cli.extract_image_references')
    def test_extract_image_references(self, extract_image_references):
        main(['extract', 'my-manifest-dir'])
        extract_image_references.assert_called_with('my-manifest-dir', output=mock.ANY)

    @mock.patch('operator_manifest.cli.resolve_image_references')
    def test_resolve_image_references(self, resolve_image_references, tmp_path):
        images_file = tmp_path / 'images.json'
        images_file.write_text('')
        main(['resolve', str(images_file)])
        resolve_image_references.assert_called_with(mock.ANY, authfile=None, output=mock.ANY)
        assert resolve_image_references.call_args[0][0].name == str(images_file)

    @mock.patch('operator_manifest.cli.replace_image_references')
    def test_replace_image_references(self, replace_image_references, tmp_path):
        replacements_file = tmp_path / 'replacements.json'
        replacements_file.write_text('')
        main(['replace', 'my-manifest-dir', str(replacements_file)])
        replace_image_references.assert_called_with('my-manifest-dir', mock.ANY, dry_run=False)

    @mock.patch('operator_manifest.cli.pin_image_references')
    def test_pin_image_references(self, pin_image_references, tmp_path):
        main(['pin', 'my-manifest-dir'])
        pin_image_references.assert_called_with(
            'my-manifest-dir',
            authfile=None,
            dry_run=False,
            output_extract=mock.ANY,
            output_replace=mock.ANY,
        )

    def test_pin_disallow_stdout_for_output_replace(self, tmp_path):
        with pytest.raises(ValueError, match=r'Cannot use stdout for --output-replace parameter'):
            main(['pin', 'my-manifest-dir', '--output-replace', '-'])

    def test_pin_disallow_stdout_for_output_extract(self, tmp_path):
        with pytest.raises(ValueError, match=r'Cannot use stdout for --output-extract parameter'):
            main(['pin', 'my-manifest-dir', '--output-extract', '-'])

    @mock.patch('operator_manifest.cli._make_parser')
    def test_insufficient_parameters(self, _make_parser):
        parser = mock.MagicMock()
        _make_parser.return_value = parser
        main([])
        parser.error.assert_called_with('Insufficient parameters! See usage above')
