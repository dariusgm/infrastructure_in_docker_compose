# Creates the read-only Paperless user "metrics" for prometheus-paperless-exporter, and prints its
# API token as TOKEN=<value>. Run it once, or again to print the token of the existing user:
#   docker compose -f compose.yaml exec -T paperless python3 /usr/src/paperless/src/manage.py shell < monitoring/paperless/create-metrics-user.py
# The user gets only the view_* permissions, so it can read the statistics and cannot change anything.
from django.contrib.auth.models import Permission, User
from rest_framework.authtoken.models import Token

user, created = User.objects.get_or_create(username="metrics")
if created:
    user.set_unusable_password()
user.is_active = True
# Staff status is needed for the logs endpoint (it answers 403 without it). Still no superuser and no
# change permissions: the user only has the view_* permissions below.
user.is_staff = True
user.is_superuser = False
user.save()
user.user_permissions.set(Permission.objects.filter(codename__startswith="view_"))

token, _ = Token.objects.get_or_create(user=user)
print("TOKEN=" + token.key)
