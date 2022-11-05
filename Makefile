.PHONY: build install test isort black flake8 typecheck bandit safety lint security

POETRY := poetry
PRECOMMIT := pre-commit

build:
	$(POETRY) build
install:
	$(POETRY) install
test:
	$(POETRY) run pytest
isort:
	$(PRECOMMIT) run isort --all-files
black:
	$(PRECOMMIT) run black --all-files
flake8:
	$(PRECOMMIT) run flake8 --all-files
typecheck:
	$(POETRY) run mypy aiosmtplib
bandit:
	$(POETRY) run bandit -n 10 -x tests ./
safety:
	$(POETRY) run safety check
lint: flake8 isort black
security: safety bandit
