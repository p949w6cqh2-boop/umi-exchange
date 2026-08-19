.PHONY: run test migrate shell lint format clean state-stamp check-state-stamp

# Run the Django development server
run:
	.venv/bin/python manage.py runserver

# Run the pytest test suite
test:
	.venv/bin/pytest

# Run database migrations
migrate:
	.venv/bin/python manage.py migrate

# Open the Django shell
shell:
	.venv/bin/python manage.py shell

# Lint the codebase using ruff (mirrors CI: style check + format check + stamp)
lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
	.venv/bin/python scripts/check_state_stamp.py

# Check STATE.md's header stamp on its own. Skips silently unless STATE.md
# is one of the files this branch changes.
check-state-stamp:
	.venv/bin/python scripts/check_state_stamp.py

# Rewrite STATE.md's header stamp to name this branch's merge-base with main.
# This is the fix the check tells you to run.
state-stamp:
	.venv/bin/python scripts/check_state_stamp.py --write

# Format the codebase using ruff
format:
	.venv/bin/ruff format .

# Clean temporary files
clean:
	find . -type d -name "__pycache__" -exec rm -r {} +
	find . -type f -name "*.py[co]" -delete
	rm -rf .pytest_cache .ruff_cache htmlcov
