#!/usr/bin/env python3
"""
Pre-build script for MkDocs documentation.

This script runs before building the documentation and:
- Generates API documentation from docstrings using pydoc-markdown
- Ensures required directories exist
"""

import sys
import subprocess
from pathlib import Path


def main():
    """Main pre-build function."""
    # Get the docs directory and project root
    docs_dir = Path(__file__).parent
    project_root = docs_dir.parent
    
    print("Running pre-build script...")
    print(f"Documentation directory: {docs_dir}")
    print(f"Project root: {project_root}")
    
    # Ensure required directories exist
    required_dirs = [
        docs_dir / "getting-started",
        docs_dir / "configuration",
        docs_dir / "usage",
        docs_dir / "advanced",
        docs_dir / "api",
    ]
    
    for dir_path in required_dirs:
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"Ensured directory exists: {dir_path}")
    
    # Generate API documentation from docstrings
    print("\nGenerating API documentation from docstrings...")
    config_file = project_root / "pydoc-markdown.yml"
    api_dir = docs_dir / "api"
    api_dir.mkdir(parents=True, exist_ok=True)
    
    if not config_file.exists():
        print(f"Warning: pydoc-markdown config not found at {config_file}")
        print("Skipping API documentation generation.")
    else:
        try:
            # Use -p flag to only document django_rls package
            result = subprocess.run(
                ["pydoc-markdown", "-p", "django_rls", "--render-toc"],
                cwd=project_root,
                check=True,
                capture_output=True,
                text=True,
            )
            
            # Write the output to docs/api/index.md
            output_file = api_dir / "index.md"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(result.stdout)
            
            print(f"API documentation generated successfully: {output_file}")
        except subprocess.CalledProcessError as e:
            print(f"Warning: Failed to generate API documentation: {e}")
            if e.stdout:
                print(f"stdout: {e.stdout}")
            if e.stderr:
                print(f"stderr: {e.stderr}")
            # Don't fail the build if API docs generation fails
        except FileNotFoundError:
            print("Warning: pydoc-markdown not found. Skipping API documentation generation.")
            print("Install it with: uv add --dev pydoc-markdown[novella]")
    
    print("\nPre-build script completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

