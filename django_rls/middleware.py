import uuid
import logging
from django.utils.deprecation import MiddlewareMixin
from django.db import connection
from django.conf import settings as django_settings
from typing import Any, Dict

from django_rls.settings_type import DjangoRLSSettings
from django_rls.constants import RlsWildcard, DBSafeValue, RLSValue

logger = logging.getLogger(__name__)


class RLSMiddleware(MiddlewareMixin):
    """
    Middleware that sets PostgreSQL session variables based on RLS context.

    - If BYPASS_CHECK_RESOLVER returns True, sets all session vars to RlsWildcard.ALL.
    - Otherwise uses VALUE_RESOLVER to fetch per-field RLS values.
    - Only sets session vars for fields in RLS_FIELDS.

    These variables are used in PostgreSQL RLS policies with current_setting().
    """

    def process_request(self, request: Any):
        rls_settings: DjangoRLSSettings = getattr(
            django_settings, "DJANGO_RLS", DjangoRLSSettings()
        )

        # Skip if not using PostgreSQL (RLS is PostgreSQL-only)
        if connection.vendor != "postgresql":
            return

        # 1. Bypass check
        rls_context: Dict[str, RLSValue]
        if rls_settings.BYPASS_CHECK_RESOLVER(request):
            rls_context = {
                field: RlsWildcard.ALL for field in rls_settings.RLS_FIELDS
            }
        else:
            rls_context = rls_settings.REQUEST_RESOLVER(request)

        # 2. Validate resolver return values
        # Warn if resolver returns fields not in RLS_FIELDS
        unexpected_fields = set(rls_context.keys()) - set(rls_settings.RLS_FIELDS)
        if unexpected_fields:
            logger.warning(
                f"REQUEST_RESOLVER returned fields not in RLS_FIELDS: {unexpected_fields}. "
                f"These will be ignored. Configured RLS_FIELDS: {rls_settings.RLS_FIELDS}"
            )

        # 3. Set PostgreSQL session vars
        with connection.cursor() as cursor:
            for field, value in rls_context.items():
                if field not in rls_settings.RLS_FIELDS:
                    continue

                db_value: DBSafeValue
                if isinstance(value, RlsWildcard):
                    db_value = value.value  # e.g., SPECIAL_CASE_ALL
                elif value is None:
                    db_value = RlsWildcard.NONE.value
                else:
                    # PostgreSQL session variables are text, and UUIDs need to be cast in RLS policies
                    if isinstance(value, uuid.UUID):
                        db_value = str(value)
                    else:
                        db_value = value

                session_key = f"{rls_settings.SESSION_NAMESPACE_PREFIX}.{field}"
                cursor.execute(f"SET {session_key} = %s", [db_value])
