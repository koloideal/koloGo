
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
    uv run python -m seatbot


watch:
    uv run watchfiles --filter python 'python -m seatbot' src


# ==============================================================================
# Quality
# ==============================================================================
lint:
    uv run ruff check src
    uv run isort --check-only src

format:
    uv run ruff format src
    uv run isort src

typecheck:
    uv run mypy src
