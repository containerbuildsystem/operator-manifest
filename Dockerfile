FROM registry.access.redhat.com/ubi8/python-39:1

LABEL \
    summary="A tool for processing operator manifests" \
    description="Use the operator-manifest binary within the image to extract, resolve, and replace image references in ClusterServiceVersion files." \
    io.k8s.description="Use the operator-manifest binary within the image to extract, resolve, and replace image references in ClusterServiceVersion files." \
    io.k8s.display-name="operator-manifest" \
    maintainer="https://github.com/containerbuildsystem" \
    vcs-url="https://github.com/containerbuildsystem/operator-manifest.git" \
    # Clear out the vcs-ref from the parent image
    vcs-ref=""

USER 0
RUN dnf install -y \
    --setopt=deltarpm=0 \
    --setopt=install_weak_deps=false \
    --setopt=tsflags=nodocs \
    skopeo \
    && dnf clean all

USER 1001
WORKDIR /opt/app-root/src
COPY . .
RUN \
    pip install -r requirements.txt  --no-cache-dir --no-deps --require-hashes && \
    pip install . --no-deps --no-cache-dir

WORKDIR /opt/app-root/workdir
CMD ["operator-manifest", "--help"]
