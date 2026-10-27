# Static start page with links to the web interfaces of the stack. See README.md at the root.
# Pinned by version and digest. Serves on 8080, because ports below 1024 need root.
FROM docker.io/library/nginx:1.29-alpine@sha256:5616878291a2eed594aee8db4dade5878cf7edcb475e59193904b198d9b830de

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
