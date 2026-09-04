ARG POSTGRES_IMAGE=postgres:17.11-trixie@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675
ARG POSTGIS_LAYER=ghcr.io/pglayers/pgx-postgis:17@sha256:e86a5818eb6ccad49ce4544fc5716a10138aaed5bfcb476d7ff6404e9086ee09

FROM ${POSTGIS_LAYER} AS postgis
FROM ${POSTGRES_IMAGE}

COPY --from=postgis / /
COPY init/010-extensions.sql /docker-entrypoint-initdb.d/010-extensions.sql
