# Validation Scripts

This directory contains validation scripts for code quality and schema validation.

## Pydantic Schema Validator

**File**: `validate_pydantic_schemas.py`

Validates Pydantic v2 schema definitions in `src/agents/schemas/` to ensure:
- All schema classes inherit from `BaseModel`
- Fields have proper type annotations
- Classes have docstrings (warning)
- Pydantic v2 `model_config` is defined (warning)

### Usage

**As pre-commit hook** (automatic):
```bash
# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Hooks run automatically on git commit
git commit -m "Add new schema"
```

**Manual execution**:
```bash
# Validate specific file
python scripts/validation/validate_pydantic_schemas.py src/agents/schemas/agent_message.py

# Validate all schema files
python scripts/validation/validate_pydantic_schemas.py src/agents/schemas/*.py
```

### Validation Rules

**Errors** (block commit):
- Missing type annotations on fields
- Syntax errors in Python code

**Warnings** (allow commit):
- Missing class docstrings
- Missing Pydantic v2 `model_config`

## Pre-Commit Configuration

The project uses pre-commit hooks for automated code quality checks:

**Configured hooks**:
- `trailing-whitespace`: Remove trailing whitespace
- `end-of-file-fixer`: Ensure files end with newline
- `check-yaml`, `check-json`: Validate YAML/JSON syntax
- `check-ast`: Validate Python syntax
- `black`: Python code formatting (line length 100)
- `isort`: Import sorting (black profile)
- `flake8`: Python linting
- `mypy`: Static type checking
- `bandit`: Security vulnerability scanning
- `validate-pydantic-schemas`: Custom Pydantic validation (this script)
- `hadolint-docker`: Dockerfile linting

### Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Install pre-commit hooks
pre-commit install

# Run hooks manually on all files
pre-commit run --all-files

# Run specific hook
pre-commit run validate-pydantic-schemas --all-files
```

### Skipping Hooks

```bash
# Skip all hooks for emergency commit
git commit --no-verify -m "Emergency fix"

# Skip specific hook
SKIP=validate-pydantic-schemas git commit -m "WIP schema"
```

## Future Validation Scripts

Planned additions:
- `validate_agent_configs.py`: Validate agent YAML configurations
- `validate_rl_configs.py`: Validate RL training configurations
- `validate_api_contracts.py`: Validate API request/response schemas
