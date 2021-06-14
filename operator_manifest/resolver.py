# SPDX-License-Identifier: BSD-3-Clause
import functools
import hashlib
import json
import logging
import os.path
import subprocess


logger = logging.getLogger(__name__)


def resolve_image_reference(image_reference, authfile=None):
    """
    Resolve the image reference to a digest image reference.

    :param str image_reference: the image reference of the container image to resolve
    :param str authfile: the path of the authentication file for registry communication.
    :return: the image reference resolved to a digest
    :rtype: str
    """
    extra_args = []
    if authfile:
        if not os.path.exists(authfile):
            raise ValueError(f'Specified authfile {authfile} does not exist')
        extra_args.append('--authfile')
        extra_args.append(authfile)

    logger.debug('Resolving %s', image_reference)
    name = _get_container_image_name(image_reference)
    skopeo_raw = _skopeo_inspect(f'docker://{image_reference}', '--raw', *extra_args)
    if json.loads(skopeo_raw).get('schemaVersion') == 2:
        raw_digest = hashlib.sha256(skopeo_raw.encode('utf-8')).hexdigest()
        digest = f'sha256:{raw_digest}'
    else:
        # Schema 1 is not a stable format. The contents of the manifest may change slightly
        # between requests causing a different digest to be computed. Instead, let's leverage
        # skopeo's own logic for determining the digest in this case. In the future, we
        # may want to use skopeo in all cases, but this will have significant performance
        # issues until https://github.com/containers/skopeo/issues/785
        digest = json.loads(_skopeo_inspect(f'docker://{image_reference}', *extra_args))['Digest']
    resolved_image_reference = f'{name}@{digest}'
    logger.debug('%s resolved to %s', image_reference, resolve_image_reference)
    return resolved_image_reference


def _get_container_image_name(image_reference):
    """
    Get the container image name from an image reference.

    :param str image_reference: the image reference to analyze
    :return: the container image name
    """
    if '@' in image_reference:
        return image_reference.split('@', 1)[0]
    else:
        return image_reference.rsplit(':', 1)[0]


def _retry(attempts=3, wait_on=Exception):
    """
    Decorator to retry a function, or method, until success or max attempts are reached.

    Note that there is no delay between attempts.

    :param int attempts: the total number of attempts to make before erroring out
    :param Exception wait_on: the exception on encountering which the function will be retried
    :raises Exception: if the maximum attempts are reached
    """

    def wrapper(function):
        @functools.wraps(function)
        def inner(*args, **kwargs):
            remaining_attempts = attempts
            while True:
                try:
                    return function(*args, **kwargs)
                except wait_on:
                    remaining_attempts -= 1
                    if remaining_attempts <= 0:
                        raise

        return inner

    return wrapper


@_retry(wait_on=ValueError)
def _skopeo_inspect(*args):
    """
    Wrap the ``skopeo inspect`` command.

    :param args: any arguments to pass to ``skopeo inspect``
    :return: the output of the ``skopeo inspect`` command
    :rtype: str
    """
    exc_msg = None
    for arg in args:
        if arg.startswith('docker://'):
            exc_msg = f'Failed to inspect {arg}. Make sure it exists and is accessible.'
            break

    skopeo_timeout = '300s'
    cmd = ['skopeo', '--command-timeout', skopeo_timeout, 'inspect'] + list(args)
    return _run_cmd(cmd, exc_msg=exc_msg)


def _run_cmd(cmd, params=None, exc_msg=None):
    """
    Run the given command with the provided parameters.

    :param iter cmd: iterable representing the command to be executed
    :param dict params: keyword parameters for command execution
    :param str exc_msg: an optional exception message when the command fails
    :return: the command output
    :rtype: str
    :raises ValueError: if the command fails
    """
    exc_msg = exc_msg or 'An unexpected error occurred'
    if not params:
        params = {}
    params.setdefault('universal_newlines', True)
    params.setdefault('encoding', 'utf-8')
    params.setdefault('stderr', subprocess.PIPE)
    params.setdefault('stdout', subprocess.PIPE)

    response = subprocess.run(cmd, **params)

    if response.returncode != 0:
        logger.error(response.stderr)
        raise ValueError(exc_msg)

    return response.stdout
