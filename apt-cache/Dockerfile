# Ubuntu package cache: apt-cacher-ng on port 3142.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends apt-cacher-ng util-linux \
 && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 0755 /usr/local/bin/entrypoint.sh

EXPOSE 3142

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
