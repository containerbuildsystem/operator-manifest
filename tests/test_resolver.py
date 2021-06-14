# SPDX-License-Identifier: BSD-3-Clause
import pytest
from unittest import mock

from operator_manifest.resolver import resolve_image_reference


class TestResolver:
    @mock.patch('subprocess.run')
    def test_resolve_schema_version_2(self, subprocess_run):
        subprocess_run.return_value = mock.Mock(returncode=0, stdout='{"schemaVersion": 2}')
        # This is the digest of the manifest itself
        expected = (
            'example.com/foo/bar@'
            'sha256:c5d902c53b4afcf32ad746fd9d696431650d3fbe8f7b10ca10519543fefd772c'
        )
        resolved = resolve_image_reference('example.com/foo/bar:latest')
        assert resolved == expected
        subprocess_run.assert_called_once()
        assert '--raw' in subprocess_run.call_args[0][0]

    @mock.patch('subprocess.run')
    def test_resolve_schema_version_1(self, subprocess_run):
        subprocess_run.side_effect = [
            mock.Mock(returncode=0, stdout='{"schemaVersion": 1}'),
            mock.Mock(returncode=0, stdout='{"Digest": "sha256:1"}'),
        ]
        # The digest determined by skopeo
        expected = 'example.com/foo/bar@sha256:1'
        resolved = resolve_image_reference('example.com/foo/bar:latest')
        assert resolved == expected
        assert subprocess_run.call_count == 2
        # The first call to skopeo uses --raw
        assert '--raw' in subprocess_run.call_args_list[0][0][0]
        # The second call to skopeo does not use --raw and relies on skopeo to determine digest
        assert '--raw' not in subprocess_run.call_args_list[1][0][0]

    @mock.patch('subprocess.run')
    def test_resolve_from_digest(self, subprocess_run):
        subprocess_run.return_value = mock.Mock(returncode=0, stdout='{"schemaVersion": 2}')
        # This is the digest of the manifest itself
        image_reference = (
            'example.com/foo/bar@'
            'sha256:c5d902c53b4afcf32ad746fd9d696431650d3fbe8f7b10ca10519543fefd772c'
        )
        # Note that the image reference being resolved is already resolved.
        resolved = resolve_image_reference(image_reference)
        assert resolved == image_reference
        subprocess_run.assert_called_once()
        assert '--raw' in subprocess_run.call_args[0][0]

    @mock.patch('subprocess.run')
    def test_authfile_usage(self, subprocess_run, tmp_path):
        image_reference = 'example.com/foo/bar:latest'
        subprocess_run.return_value = mock.Mock(returncode=0, stdout='{"schemaVersion": 2}')
        authfile = tmp_path / 'auth.json'
        authfile.write_text('spam')
        resolve_image_reference(image_reference, authfile=str(authfile))

        subprocess_run.assert_called_once()
        # The first parameter, command args, for the first call to subprocess.run
        args = subprocess_run.call_args[0][0]
        # Ensure the command args contain [..., "--authfile", <path-to-authfile>, ...]
        assert args.index('--authfile') + 1 == args.index(str(authfile))

    @mock.patch('subprocess.run')
    def test_missing_authfile(self, subprocess_run, tmp_path):
        authfile = tmp_path / 'auth.json'
        assert not authfile.exists()
        with pytest.raises(ValueError, match=r'Specified authfile .* does not exist'):
            resolve_image_reference('example.com/foo/bar:latest', authfile=str(authfile))
        subprocess_run.assert_not_called()

    @mock.patch('subprocess.run')
    def test_command_retry(self, subprocess_run):
        subprocess_run.side_effect = [
            mock.Mock(returncode=1),
            mock.Mock(returncode=1),
            mock.Mock(returncode=0, stdout='{"schemaVersion": 2}'),
        ]
        resolve_image_reference('example.com/foo/bar:latest')
        assert subprocess_run.call_count == 3

    @mock.patch('subprocess.run')
    def test_command_retry_but_give_up(self, subprocess_run):
        subprocess_run.return_value = mock.Mock(returncode=1)
        with pytest.raises(ValueError, match=r'Failed to inspect'):
            resolve_image_reference('example.com/foo/bar:latest')
        assert subprocess_run.call_count == 3
