# Contributing

Agentic contributions to aiosmtplib must follow the project style. Keep code clear and concise,
and avoid excessive commenting.


# Tests and Validation

All changes must be formatted via ruff and pass linting and typechecks. Use the commands defined
in pyproject.toml via the `poe` command runner, invoked as `uvx --from poethepoet poe <task>`
(poe is not in requirements-dev.txt). Tasks run against the project `.venv`, so create it with
`uv venv` and `uv pip install -r requirements-dev.txt -e .` first.
