import warnings
from django.apps import apps
from django.conf import settings as django_settings
from django_rls.settings_type import DjangoRLSSettings

django_rls_settings: DjangoRLSSettings

if user_settings := getattr(django_settings, "DJANGO_RLS", False):
    if isinstance(user_settings, DjangoRLSSettings):
        django_rls_settings = user_settings
    else:
        raise Exception(
            f"DJANGO_RLS must be of type DjangoRLSSettings, "
            f"but got {type(user_settings)}"
        )
else:
    warnings.warn(
        "You have not provided any custom Django RLS settings. Falling back to defaults.",
        RuntimeWarning,
    )
    django_rls_settings = DjangoRLSSettings()


# Validations
if django_rls_settings.USE_DB_MIGRATION_USER:
    if not django_rls_settings.MIGRATION_USER or not django_rls_settings.MIGRATION_PASSWORD:
        raise Exception(
            "USE_DB_MIGRATION_USER is True, but MIGRATION_USER or MIGRATION_PASSWORD is not set"
        )
