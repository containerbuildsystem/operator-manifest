# Operator Manifest

A python library for processing operator manifests.

## Pull Specifications

The `OperatorManifest` class can be used to identify and modify all the container image pull
specifications found in an operator
[Cluster Service Version](https://operator-framework.github.io/olm-book/docs/glossary.html#clusterserviceversion),
CSV, file. Below is a comprehensive list of the different locations within a CSV file where the
pull specifications are searched for by `OperatorManifest`:

1. RelatedImage: `spec.relatedImages[].image`
2. Annotation: any of:
   1. `metadata.annotations.containerImage`
   2. `metadata.annotations[]` for any given Object where the annotation value contains one
      or more image pull specification.
3. Container: `spec.install.spec.deployments[].spec.template.spec.containers[].image`
4. InitContainer: `spec.install.spec.deployments[].spec.template.spec.initContainers[].image`
5. RelatedImageEnv: `spec.install.spec.deployments[].spec.template.spec.containers[].env[].value`
   and `spec.install.spec.deployments[].spec.template.spec.initContainers[].env[].value` where the
   `name` of the corresponding env Object is prefixed by `RELATED_IMAGE_`.


NOTE: The Object paths listed above follow the [jq](https://stedolan.github.io/jq/manual/) syntax
for iterating through Objects and Arrays. For example, `spec.relatedImages[].image` indicates the
`image` attribute of every Object listed under the `relatedImages` Array which, in turn, is an
attribute in the `spec` Object.

When an Operator bundle image is built, the `RelatedImages` should represent the full list of
container image pull specifications. The `OperatorManifest` class provides the mechanism to
ensure this is consistently done. It's up to each build system to make the necessary calls to
`OperatorManifest`. In some cases the build system, e.g.
[OSBS](https://osbs.readthedocs.io/en/latest/), may want fully control the content of
`RelatedImages` and will purposely cause failures if `RelatedImages` is already populated.

Another functionality of the `OperatorManifest` class is the ability to modify any of the container
image pull specifications identified. This is useful for performing container registry translations
and pinning floating tags to a specific digest.

## Running the Unit Tests

The testing environment is managed by [tox](https://tox.readthedocs.io/en/latest/). Simply run
`tox` and all the linting and unit tests will run.

If you'd like to run a specific unit test, you can do the following:

```bash
tox -e py37 tests/test_operator.py::TestOperatorCSV::test_valuefrom_references_not_allowed
```

## Dependency Management

To manage dependencies, this project uses [pip-tools](https://github.com/jazzband/pip-tools) so that
the production dependencies are pinned and the hashes of the dependencies are verified during
installation.

The unpinned dependencies are recorded in `setup.py`, and to generate the `requirements.txt` file,
run `pip-compile --generate-hashes --output-file=requirements.txt`. This is only necessary when
adding a new package. To upgrade a package, use the `-P` argument of the `pip-compile` command.

To update `requirements-test.txt`, run
`pip-compile --generate-hashes requirements-test.in -o requirements-test.txt`.

When installing the dependencies in a production environment, run
`pip install --require-hashes -r requirements.txt`. Alternatively, you may use
`pip-sync requirements.txt`, which will make sure your virtualenv only has the packages listed in
`requirements.txt`.

