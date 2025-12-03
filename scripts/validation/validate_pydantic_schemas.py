#!/usr/bin/env python3
"""
Pydantic Schema Validation Script for Pre-Commit Hook
Validates that all Pydantic schemas in src/agents/schemas/ are properly defined.
"""

import ast
import sys
from pathlib import Path
from typing import List, Set


class PydanticSchemaValidator(ast.NodeVisitor):
    """AST visitor to validate Pydantic schema definitions."""

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.has_basemodel_import = False
        self.basemodel_classes: Set[str] = set()

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Check for Pydantic BaseModel imports."""
        if node.module == "pydantic":
            for alias in node.names:
                if alias.name == "BaseModel":
                    self.has_basemodel_import = True
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Validate Pydantic model classes."""
        # Check if class inherits from BaseModel
        is_basemodel = any(
            isinstance(base, ast.Name) and base.id == "BaseModel"
            for base in node.bases
        )

        if is_basemodel:
            self.basemodel_classes.add(node.name)
            self._validate_basemodel_class(node)

        self.generic_visit(node)

    def _validate_basemodel_class(self, node: ast.ClassDef) -> None:
        """Validate a Pydantic BaseModel class definition."""
        # Check for docstring
        if not ast.get_docstring(node):
            self.warnings.append(
                f"Class {node.name} is missing a docstring (line {node.lineno})"
            )

        # Check for ConfigDict or Config class
        has_config = False
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                if item.target.id == "model_config":
                    has_config = True
            elif isinstance(item, ast.ClassDef) and item.name == "Config":
                has_config = True

        if not has_config:
            self.warnings.append(
                f"Class {node.name} should define model_config for Pydantic v2 settings "
                f"(line {node.lineno})"
            )

        # Check field definitions
        for item in node.body:
            if isinstance(item, ast.AnnAssign):
                self._validate_field(item, node.name)

    def _validate_field(self, node: ast.AnnAssign, class_name: str) -> None:
        """Validate a Pydantic field definition."""
        if not isinstance(node.target, ast.Name):
            return

        field_name = node.target.id

        # Skip private fields and config
        if field_name.startswith("_") or field_name == "model_config":
            return

        # Check for type annotation
        if node.annotation is None:
            self.errors.append(
                f"Field {class_name}.{field_name} is missing type annotation "
                f"(line {node.lineno})"
            )

        # Check for Field() usage with validation
        if node.value and isinstance(node.value, ast.Call):
            if isinstance(node.value.func, ast.Name) and node.value.func.id == "Field":
                # Good: using Field() for validation
                pass


def validate_file(filepath: Path) -> tuple[List[str], List[str]]:
    """
    Validate a single Python file for Pydantic schema correctness.

    Args:
        filepath: Path to the Python file to validate

    Returns:
        Tuple of (errors, warnings)
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(filepath))

        validator = PydanticSchemaValidator(filepath)
        validator.visit(tree)

        return validator.errors, validator.warnings

    except SyntaxError as e:
        return [f"Syntax error in {filepath}: {e}"], []
    except Exception as e:
        return [f"Error processing {filepath}: {e}"], []


def main() -> int:
    """
    Main entry point for pre-commit hook.

    Args from sys.argv are file paths to validate.

    Returns:
        0 if all validations pass, 1 if there are errors
    """
    if len(sys.argv) < 2:
        print("Usage: validate_pydantic_schemas.py <file1> <file2> ...")
        return 0

    filepaths = [Path(arg) for arg in sys.argv[1:]]

    total_errors = 0
    total_warnings = 0

    for filepath in filepaths:
        if not filepath.exists():
            print(f"⚠️  File not found: {filepath}")
            continue

        errors, warnings = validate_file(filepath)

        if errors:
            print(f"\n❌ ERRORS in {filepath}:")
            for error in errors:
                print(f"  - {error}")
            total_errors += len(errors)

        if warnings:
            print(f"\n⚠️  WARNINGS in {filepath}:")
            for warning in warnings:
                print(f"  - {warning}")
            total_warnings += len(warnings)

    # Summary
    if total_errors > 0 or total_warnings > 0:
        print(f"\n📊 Summary:")
        print(f"  Errors: {total_errors}")
        print(f"  Warnings: {total_warnings}")

    if total_errors > 0:
        print("\n❌ Pydantic schema validation FAILED")
        return 1
    elif total_warnings > 0:
        print("\n✅ Pydantic schema validation PASSED (with warnings)")
        return 0
    else:
        print("\n✅ Pydantic schema validation PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
