from django.apps import AppConfig


class DjangoRLSConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_rls"
    verbose_name = "Django RLS"

    def ready(self):
        from django_rls.migration_hook import configure_rls_migration_user
        configure_rls_migration_user()