import re
import os
import ast
from django.core.management.commands.makemigrations import Command as MakeMigrationsCommand
from django.db import migrations
from django.conf import settings as django_settings
from django_rls.settings_type import DjangoRLSSettings
from django_rls.utils import build_rls_using_clause, get_field_sql_type
import questionary

# Import exception for non-interactive environments
try:
    from prompt_toolkit.output.win32 import NoConsoleScreenBufferError  # type: ignore[attr-defined]
except (ImportError, AssertionError, AttributeError):
    # On non-Windows or if prompt_toolkit changes, use OSError as fallback
    NoConsoleScreenBufferError = OSError

class Command(MakeMigrationsCommand):
    def write_migration_files(self, changes):
        # Hook into the migration writing process
        self.inject_rls_operations(changes)
        super().write_migration_files(changes)
        # Post-process migration files to format SQL with triple quotes
        self._format_migration_sql(changes)

    def inject_rls_operations(self, changes):
        rls_settings: DjangoRLSSettings = getattr(
            django_settings, "DJANGO_RLS", DjangoRLSSettings()
        )
        tenant_apps = rls_settings.TENANT_APPS
        
        if not tenant_apps:
            return

        for app_label, app_migrations in changes.items():
            if app_label not in tenant_apps:
                continue

            for migration in app_migrations:
                for operation in migration.operations:
                    if isinstance(operation, migrations.CreateModel):
                        self._add_rls_to_create_model(app_label, operation, rls_settings, migration)
                    # TODO: Handle AddField if it adds a tenant_id to an existing model?
                    # For now, focus on new models as per request "on new migrations" (implied new tables)

    def _add_rls_to_create_model(self, app_label, operation, rls_settings, migration):
        model_name = operation.name
        fields_dict = dict(operation.fields)
        
        # Find available fields that match configured RLS_FIELDS
        available_fields = []
        for rls_field in rls_settings.RLS_FIELDS:
             if rls_field in fields_dict:
                  available_fields.append(rls_field)
        
        if not available_fields:
            return

        enforce_fields = []
        
        # If interactive, prompt user for field selection
        # Check both self.interactive and if we can actually use questionary
        if self.interactive and len(available_fields) > 0:
             try:
                 enforce_fields = self._prompt_for_fields(model_name, available_fields, app_label)
             except (NoConsoleScreenBufferError, OSError, RuntimeError) as e:
                 # Fallback if questionary can't initialize (e.g., in tests without proper console)
                 self.stdout.write(self.style.WARNING(f"RLS: Cannot prompt interactively ({type(e).__name__}). Using all fields: {available_fields}"))
                 enforce_fields = available_fields
        else:
             # Non-interactive (e.g. CI/CD): default to all found fields
             enforce_fields = available_fields
        
        if not enforce_fields:
            self.stdout.write(self.style.WARNING(f"RLS: Skipping RLS for {model_name} (No fields selected)."))
            return

        # Build SQL
        # Use the same field type mapping as utils.get_field_sql_type for consistency
        from django_rls.utils import FIELD_TYPE_MAPPING
        field_types = {}
        for field_name in enforce_fields:
            field_instance = fields_dict[field_name]
            internal_type = field_instance.get_internal_type()
            sql_type = FIELD_TYPE_MAPPING.get(internal_type, "text")
            field_types[field_name] = sql_type

        using_clause = build_rls_using_clause(
            enforce_fields, 
            field_types, 
            rls_settings.SESSION_NAMESPACE_PREFIX
        )
        
        options = operation.options
        db_table = options.get("db_table")
        if not db_table:
             db_table = f"{app_label}_{model_name.lower()}"
        
        policy_name = f"{db_table}_rls_policy"
        
        # Format SQL - each statement on a single line for RunSQL compatibility
        # Use FOR ALL with both USING (for SELECT) and WITH CHECK (for INSERT/UPDATE)
        sql_lines = [
            f'DROP POLICY IF EXISTS "{policy_name}" ON "{db_table}";',
            f'CREATE POLICY "{policy_name}" ON "{db_table}" FOR ALL USING ({using_clause}) WITH CHECK ({using_clause});',
            f'ALTER TABLE "{db_table}" ENABLE ROW LEVEL SECURITY;',
            f'ALTER TABLE "{db_table}" FORCE ROW LEVEL SECURITY;',
        ]
        sql = '\n'.join(sql_lines)
        
        reverse_sql_lines = [
            f'ALTER TABLE "{db_table}" NO FORCE ROW LEVEL SECURITY;',
            f'ALTER TABLE "{db_table}" DISABLE ROW LEVEL SECURITY;',
            f'DROP POLICY IF EXISTS "{policy_name}" ON "{db_table}";',
        ]
        reverse_sql = '\n'.join(reverse_sql_lines)
        
        migration_op = migrations.RunSQL(sql, reverse_sql)
        operation_index = migration.operations.index(operation)
        migration.operations.insert(operation_index + 1, migration_op)
        
        self.stdout.write(self.style.SUCCESS(f"RLS: Added policy for {model_name} enforcing {enforce_fields}"))

    def _prompt_for_fields(self, model_name, available_fields, app_label):
        """Prompt user to select RLS fields using checkbox interface."""
        self.stdout.write(f"\nRLS Configuration for {model_name} (in {app_label})")
        
        # Create choices with all fields checked by default
        choices = [
            questionary.Choice(
                title=field,
                value=field,
                checked=True  # Default to all selected
            ) 
            for field in available_fields
        ]
        
        answer = questionary.checkbox(
            f"Select RLS fields for {model_name}:",
            choices=choices,
            instruction="(Use <space> to toggle, <enter> to confirm)"
        ).ask()
        
        # answer is None if cancelled (Ctrl+C) or empty list if nothing selected
        return answer if answer is not None else []
    
    def _format_migration_sql(self, changes):
        """
        Post-process migration files to format RunSQL operations with triple-quoted strings.
        This makes the SQL more readable in the generated migration files.
        """
        from django.apps import apps
        
        for app_label, app_migrations in changes.items():
            for migration in app_migrations:
                # Get the migration file path by constructing it from app and migration name
                app_config = apps.get_app_config(app_label)
                migrations_dir = os.path.join(app_config.path, "migrations")
                
                # Migration name format: 0001_initial.py
                migration_name = migration.name
                migration_file = os.path.join(migrations_dir, f"{migration_name}.py")
                
                if not os.path.exists(migration_file):
                    continue
                
                # Read the file
                with open(migration_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Find and replace sql= and reverse_sql= parameters that contain \n
                # Match sql= or reverse_sql= followed by a quoted string (single or double quotes)
                pattern = r'\b(sql|reverse_sql)=((?:"(?:[^"\\]|\\.|"")*"|\'(?:[^\'\\]|\\.|\'\')*\'))'
                
                def format_match(m):
                    full = m.group(0)
                    param = m.group(1)
                    quoted = m.group(2)
                    
                    # Only process if contains \n
                    if '\\n' not in quoted:
                        return full
                    
                    # Parse the string
                    try:
                        content = ast.literal_eval(quoted)
                    except (ValueError, SyntaxError):
                        return full
                    
                    # Format with triple quotes
                    lines = content.split('\n')
                    if len(lines) == 1:
                        return f'{param}="""{content}"""'
                    
                    formatted = '"""' + lines[0]
                    for line in lines[1:]:
                        formatted += '\n' + ' ' * 16 + line
                    formatted += '"""'
                    return f'{param}={formatted}'
                
                new_content = re.sub(pattern, format_match, content)
                
                # Write back if changed
                if new_content != content:
                    with open(migration_file, 'w', encoding='utf-8') as f:
                        f.write(new_content)
