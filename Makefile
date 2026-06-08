.PHONY: run test migrate shell lint format clean

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

# Lint the codebase using ruff
lint:
	.venv/bin/ruff check .

# Format the codebase using ruff
format:
	.venv/bin/ruff format .

# Clean temporary files
clean:
	find . -type d -name "__pycache__" -exec rm -r {} +
	find . -type f -name "*.py[co]" -delete
	rm -rf .pytest_cache .ruff_cache htmlcov
