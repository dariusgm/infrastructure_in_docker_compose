#!/usr/bin/env bash
# End-to-end test of the mail server: create a throwaway account over the JMAP API, submit a message
# over SMTP (port 465, implicit TLS, authenticated as the administrator), read it back over JMAP as
# the new account, and delete the account again. Exit status 0 means every step passed.
# Run from the repository root on the server: mail/e2e-test.sh
set -euo pipefail

cd "$(dirname "$0")/.."
env_value() { grep "^$1=" .env | head -n1 | cut -d= -f2-; }
ADMIN_USER=$(env_value MAIL_ADMIN_USER)
ADMIN_PW=$(env_value MAIL_ADMIN_PASSWORD)
HOST_IP=$(env_value HOST_IP)
DATA_DIR=$(env_value DATA_DIR)
CA="$DATA_DIR/vaultwarden-tls/ca.pem"
MAIL_HOST=mail.home.lan

ID=$(openssl rand -hex 6)
NAME="e2e-$ID"
ADDRESS="$NAME@home.lan"
PASSWORD=$(openssl rand -hex 16)
TOKEN="e2e-token-$ID"
ACCOUNT_ID=""

# JMAP call over HTTPS to the mail host, verified with the local CA: $1 user, $2 password, $3 body.
jmap() {
  curl -s --cacert "$CA" --resolve "$MAIL_HOST:443:$HOST_IP" -u "$1:$2" \
    -H 'Content-Type: application/json' -X POST "https://$MAIL_HOST/jmap/" -d "$3"
}

cleanup() {
  if [ -n "$ACCOUNT_ID" ]; then
    jmap "$ADMIN_USER" "$ADMIN_PW" \
      "{\"methodCalls\":[[\"x:Account/set\",{\"destroy\":[\"$ACCOUNT_ID\"]},\"c1\"]],\"using\":[\"urn:ietf:params:jmap:core\",\"urn:stalwart:jmap\"]}" >/dev/null
    echo "cleanup: test account deleted"
  fi
}
trap cleanup EXIT

echo "1. create the test account $ADDRESS"
DOMAIN_ID=$(jmap "$ADMIN_USER" "$ADMIN_PW" \
  '{"methodCalls":[["x:Domain/get",{"ids":null,"properties":["id","name"]},"c1"]],"using":["urn:ietf:params:jmap:core","urn:stalwart:jmap"]}' \
  | python3 -c 'import json,sys; print([d["id"] for d in json.load(sys.stdin)["methodResponses"][0][1]["list"] if d["name"]=="home.lan"][0])')
CREATE=$(jmap "$ADMIN_USER" "$ADMIN_PW" "{\"methodCalls\":[[\"x:Account/set\",{\"create\":{\"a1\":{\"@type\":\"User\",\"name\":\"$NAME\",\"domainId\":\"$DOMAIN_ID\",\"description\":\"E2E test\",\"credentials\":{\"0\":{\"@type\":\"Password\",\"secret\":\"$PASSWORD\"}},\"roles\":{\"@type\":\"User\"}}}},\"c1\"]],\"using\":[\"urn:ietf:params:jmap:core\",\"urn:stalwart:jmap\"]}")
ACCOUNT_ID=$(echo "$CREATE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["methodResponses"][0][1]["created"]["a1"]["id"])')
echo "   created account id $ACCOUNT_ID"

echo "2. send a message to $ADDRESS over SMTP (465, implicit TLS, authenticated)"
printf 'From: %s\r\nTo: %s\r\nSubject: %s\r\nDate: %s\r\nMessage-ID: <%s@home.lan>\r\n\r\nE2E body %s\r\n' \
  "$ADMIN_USER" "$ADDRESS" "$TOKEN" "$(date -R)" "$TOKEN" "$TOKEN" \
  | docker run --rm -i --network infrastructure_monitoring -v "$CA:/ca.pem:ro" docker.io/curlimages/curl:latest \
      --silent --show-error --cacert /ca.pem --connect-to "$MAIL_HOST:465:stalwart:465" \
      --url "smtps://$MAIL_HOST:465" --user "$ADMIN_USER:$ADMIN_PW" \
      --mail-from "$ADMIN_USER" --mail-rcpt "$ADDRESS" -T -
echo "   submitted"

echo "3. read the message back over JMAP as $ADDRESS"
SESSION=$(curl -s --cacert "$CA" --resolve "$MAIL_HOST:443:$HOST_IP" -u "$ADDRESS:$PASSWORD" "https://$MAIL_HOST/jmap/session")
MAIL_ACCOUNT=$(echo "$SESSION" | python3 -c 'import json,sys; print(json.load(sys.stdin)["primaryAccounts"]["urn:ietf:params:jmap:mail"])')
FOUND=""
for attempt in $(seq 1 30); do
  RESULT=$(jmap "$ADDRESS" "$PASSWORD" "{\"methodCalls\":[[\"Email/query\",{\"accountId\":\"$MAIL_ACCOUNT\",\"filter\":{\"subject\":\"$TOKEN\"}},\"c1\"],[\"Email/get\",{\"accountId\":\"$MAIL_ACCOUNT\",\"#ids\":{\"resultOf\":\"c1\",\"name\":\"Email/query\",\"path\":\"/ids\"},\"properties\":[\"subject\",\"from\",\"to\"]},\"c2\"]],\"using\":[\"urn:ietf:params:jmap:core\",\"urn:ietf:params:jmap:mail\"]}")
  if echo "$RESULT" | grep -q "$TOKEN"; then
    FOUND=yes
    break
  fi
  sleep 2
done

if [ "$FOUND" = yes ]; then
  echo "PASS: message delivered and read back (poll attempt $attempt)"
else
  echo "FAIL: message with subject $TOKEN not found in the mailbox" >&2
  exit 1
fi
