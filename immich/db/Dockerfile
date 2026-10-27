# PostgreSQL 18 for Immich, with pgvector and VectorChord. See immich/README.md.
#
# Built on the official image, pinned to a release. pgvector is compiled from its
# source tag, VectorChord is installed from its release .deb. Both are checked against
# a SHA256 sum, so a changed download fails the build.
FROM docker.io/library/postgres:18.6-trixie

ARG TARGETARCH
# pgvector 0.8.5 is the version that VectorChord 1.1.1 is released with.
ARG PGVECTOR_VERSION=0.8.5
ARG PGVECTOR_SHA256=6f88a5cbdde31666f4b6c1a6b75c51dcbeffe58f9a7d2b26e502d5a6e5e14d44
ARG VECTORCHORD_VERSION=1.1.1
ARG VECTORCHORD_SHA256=7637a18a97157db8d904bb7093e5ce33b6a395c0acac9ae6b660032f3d57a33e

RUN if [ "$TARGETARCH" != "amd64" ]; then echo "only amd64 is supported by this image" >&2; exit 1; fi

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends build-essential ca-certificates wget postgresql-server-dev-18; \
    \
    # pgvector: compile against this server's pg_config, then remove the build tools again.
    wget -nv -O /tmp/pgvector.tar.gz "https://github.com/pgvector/pgvector/archive/refs/tags/v${PGVECTOR_VERSION}.tar.gz"; \
    echo "${PGVECTOR_SHA256}  /tmp/pgvector.tar.gz" | sha256sum -c -; \
    mkdir /tmp/pgvector; \
    tar -xzf /tmp/pgvector.tar.gz -C /tmp/pgvector --strip-components=1; \
    make -C /tmp/pgvector PG_CONFIG=/usr/lib/postgresql/18/bin/pg_config OPTFLAGS="" install; \
    \
    # VectorChord: prebuilt package for PostgreSQL 18, amd64.
    wget -nv -O /tmp/vchord.deb "https://github.com/supervc-stack/VectorChord/releases/download/${VECTORCHORD_VERSION}/postgresql-18-vchord_${VECTORCHORD_VERSION}-1_amd64.deb"; \
    echo "${VECTORCHORD_SHA256}  /tmp/vchord.deb" | sha256sum -c -; \
    apt-get install -y /tmp/vchord.deb; \
    \
    apt-get purge -y --auto-remove build-essential wget; \
    rm -rf /tmp/pgvector /tmp/pgvector.tar.gz /tmp/vchord.deb /var/lib/apt/lists/*

# VectorChord must be preloaded. Immich creates the extensions itself on first start.
CMD ["postgres", "-c", "shared_preload_libraries=vchord.so"]
