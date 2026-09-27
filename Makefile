# Local development tasks. `make brokers && make test` runs everything CI runs
# in its test job. The first target that needs Python creates ./venv with the
# package installed in editable mode and its dev extra.

PYTHON ?= python3
VENV ?= venv
BIN := $(VENV)/bin
RESULTS ?= results

.PHONY: brokers test test-unit test-acc docs lint clean

$(BIN)/python: pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(BIN)/python -m pip install --quiet --upgrade pip
	$(BIN)/python -m pip install --quiet -e ".[dev]"
	@touch $@

# Start the test brokers from docker-compose.yml and wait until they are
# healthy.
brokers:
	docker compose up --wait --wait-timeout 60

# Unit and acceptance tests under coverage, then the coverage report with the
# floor from pyproject.toml.
test: $(BIN)/python
	rm -f .coverage .coverage.*
	$(BIN)/python -m coverage run -m pytest tests/unit
	$(BIN)/python -m coverage run -m robot --outputdir $(RESULTS) tests/acceptance
	$(BIN)/python -m coverage combine
	$(BIN)/python -m coverage report

test-unit: $(BIN)/python
	$(BIN)/python -m pytest tests/unit

test-acc: $(BIN)/python
	$(BIN)/python -m robot --outputdir $(RESULTS) tests/acceptance

docs: $(BIN)/python
	$(BIN)/python -m robot.libdoc MQTTLibrary docs/index.html

lint: $(BIN)/python
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .
	$(BIN)/python -m robot.libdoc MQTTLibrary $(RESULTS)/MQTTLibrary.html
	$(BIN)/python -m robot --dryrun --output NONE --report NONE --log NONE tests/acceptance

clean:
	docker compose down -v
	rm -rf $(RESULTS) .coverage .coverage.* .pytest_cache .ruff_cache
