# Backup job for the stack: PostgreSQL dumps, Paperless file snapshots and Pi-hole databases.
# Based on the same PostgreSQL image as the database, so pg_dump matches the server version.
FROM docker.io/library/postgres:18.6-trixie

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends rsync sqlite3 \
 && rm -rf /var/lib/apt/lists/*

COPY backup.sh /usr/local/bin/backup.sh
RUN chmod 0755 /usr/local/bin/backup.sh

# Without an argument the job runs forever, one backup per day. "once" runs a single backup.
ENTRYPOINT ["/usr/local/bin/backup.sh"]
CMD ["loop"]
