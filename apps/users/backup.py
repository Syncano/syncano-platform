from apps.backups import site

from .models import Group, Membership, User, UserSocialProfile

site.register([Group, User, Membership, UserSocialProfile])
