.PHONY: build install test isort black flake8 pyupgrade typecheck bandit safety lint security poetry-check docs

POETRY := poetry
PRECOMMIT := pre-commit

build:
	$(POETRY) build
install:
	$(POETRY) install
test:
	$(POETRY) run pytest
isort:
	$(PRECOMMIT) run isort --all-files --show-diff-on-failure
black:
	$(PRECOMMIT) run black --all-files --show-diff-on-failure
flake8:
	$(PRECOMMIT) run flake8 --all-files --show-diff-on-failure
pyupgrade:
	$(PRECOMMIT) run pyupgrade --all-files --show-diff-on-failure
typecheck:
	$(POETRY) run mypy aiosmtplib
bandit:
	$(POETRY) run bandit -n 10 -x tests ./
safety:
	$(POETRY) run safety check
poetry-check:
	$(POETRY) check
lint: flake8 isort black pyupgrade poetry-check
security: safety bandit
docs:
	$(POETRY) run sphinx-build -nWT -b doctest -d ./docs/build/doctrees ./docs ./docs/build/html
	$(POETRY) run sphinx-build -nWT -b html -d ./docs/build/doctrees ./docs ./docs/build/html
