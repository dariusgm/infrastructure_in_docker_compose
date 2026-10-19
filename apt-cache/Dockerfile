# Ubuntu package cache: apt-cacher-ng for apt traffic and a generic nginx URL proxy
# for other downloads (for example GitHub release assets). Both run in this one image.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      apt-cacher-ng nginx ca-certificates util-linux \
 && rm -rf /var/lib/apt/lists/* \
 && rm -f /etc/nginx/sites-enabled/default

COPY nginx.conf /etc/nginx/nginx.conf
COPY entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod 0755 /usr/local/bin/entrypoint.sh \
 && install -d -o www-data -g www-data /var/cache/nginx/url_proxy

# 3142: apt-cacher-ng, 8081: URL proxy
EXPOSE 3142 8081

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
