
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]
set shell := ["bash", "-c"]


# ==============================================================================
# Default Command
# ==============================================================================
default: watch


# ==============================================================================
# Dependency Management
# ==============================================================================
install:
    uv sync

install-dev:
    uv sync --all-groups


# ==============================================================================
# Database
# ==============================================================================
migrate:
    uv run alembic upgrade head

migrate-new msg="auto":
    uv run alembic revision --autogenerate -m "{{msg}}"


# ==============================================================================
# Run Application
# ==============================================================================

run:
    uv run python -m kologo


watch:
    uv run watchfiles --filter python 'python -m kologo' src


# ==============================================================================
# Quality
# ==============================================================================
lint:
    uv run ruff check src tests
    uv run isort --check-only src tests

format:
    uv run ruff format src tests
    uv run isort src tests

typecheck:
    uv run mypy src tests

test:
    uv run pytest
