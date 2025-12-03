from typing import List, Dict
from django.db import models
from django.core.exceptions import FieldDoesNotExist
from django_rls.constants import RlsWildcard

# Centralized field type mapping for RLS policy generation
# Exported for use in makemigrations command to maintain consistency
FIELD_TYPE_MAPPING = {
    "IntegerField": "int",
    "BigIntegerField": "bigint",
    "UUIDField": "uuid",
    "CharField": "text",
    "BooleanField": "boolean",
}

def get_field_sql_type(model: models.Model, field_name: str) -> str:
    """
    Maps Django field types to PostgreSQL SQL types for RLS policy generation.
    
    Args:
        model: The Django model instance
        field_name: Name of the field to get the SQL type for
        
    Returns:
        PostgreSQL SQL type string (e.g., 'int', 'uuid', 'text')
        
    Raises:
        FieldDoesNotExist: If the field does not exist on the model
    """
    try:
        field = model._meta.get_field(field_name)
    except FieldDoesNotExist:
        model_name = model._meta.object_name
        raise FieldDoesNotExist(
            f"Field '{field_name}' does not exist on model '{model_name}'"
        )
    # GenericForeignKey doesn't have get_internal_type()
    if hasattr(field, "get_internal_type"):
        internal_type = field.get_internal_type()
        return FIELD_TYPE_MAPPING.get(internal_type, "text")
    return "text"  # Fallback for fields without get_internal_type()

def build_rls_using_clause(fields: List[str], field_types: Dict[str, str], session_prefix: str) -> str:
    """
    Constructs the RLS USING clause with wildcard and null handling for each field.
    
    Each field is wrapped in a CASE statement that handles:
    - NULL session variables (returns FALSE)
    - Empty strings (returns FALSE)
    - RlsWildcard.NONE (returns FALSE)
    - RlsWildcard.ALL (returns TRUE - bypasses RLS)
    - Normal values (compares field to session variable)
    
    Args:
        fields: List of field names to include in the RLS policy
        field_types: Dictionary mapping field names to their PostgreSQL SQL types
        session_prefix: Prefix for session variables (typically "rls")
        
    Returns:
        SQL string containing the USING clause for the RLS policy
    """
    clauses = []

    for field in fields:
        sql_type = field_types.get(field, "text")
        clause = (
            f"(\n"
            f"            CASE\n"
            f"                WHEN current_setting('{session_prefix}.{field}', true) IS NULL THEN FALSE\n"
            f"                WHEN current_setting('{session_prefix}.{field}') = '' THEN FALSE\n"
            f"                WHEN current_setting('{session_prefix}.{field}') = '{RlsWildcard.NONE.value}' THEN FALSE\n"
            f"                WHEN current_setting('{session_prefix}.{field}') = '{RlsWildcard.ALL.value}' THEN TRUE\n"
            f"                ELSE {field} = current_setting('{session_prefix}.{field}')::{sql_type}\n"
            f"            END\n"
            f"        )"
        )
        clauses.append(clause)

    return " AND\n".join(clauses)

