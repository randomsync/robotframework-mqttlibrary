# Local development tasks. `make brokers && make test` runs everything CI runs
# in its test job. The first target that needs Python creates ./venv with the
# package installed in editable mode and its dev extra.

PYTHON ?= python3
VENV ?= venv
BIN := $(VENV)/bin
RESULTS ?= results

.PHONY: brokers test test-unit test-acc docs lint clean

# A stamp file, not venv/bin/python: that is a symlink, and touching it would
# change the base interpreter's timestamp.
STAMP := $(VENV)/.installed

$(STAMP): pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(BIN)/python -m pip install --quiet --upgrade pip
	$(BIN)/python -m pip install --quiet -e ".[dev]"
	touch $@

# Start the test brokers from docker-compose.yml and wait until they are
# healthy.
brokers:
	docker compose up --wait --wait-timeout 60

# Unit and acceptance tests under coverage, then the coverage report with the
# floor from pyproject.toml.
test: $(STAMP)
	rm -f .coverage .coverage.*
	$(BIN)/python -m coverage run -m pytest tests/unit
	$(BIN)/python -m coverage run -m robot --outputdir $(RESULTS) tests/acceptance
	$(BIN)/python -m coverage combine
	$(BIN)/python -m coverage report

test-unit: $(STAMP)
	$(BIN)/python -m pytest tests/unit

test-acc: $(STAMP)
	$(BIN)/python -m robot --outputdir $(RESULTS) tests/acceptance

# With the Robot Framework pinned in the docs extra, which CI also uses to
# check docs/index.html.
docs: $(STAMP)
	$(BIN)/python -m pip install --quiet -e ".[docs]"
	$(BIN)/python -m robot.libdoc MQTTLibrary docs/index.html

# Like CI, the dry run fails on warnings as well as errors.
lint: $(STAMP)
	mkdir -p $(RESULTS)
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .
	$(BIN)/python -m robot.libdoc MQTTLibrary $(RESULTS)/MQTTLibrary.html
	$(BIN)/python -m robot --dryrun --output NONE --report NONE --log NONE \
		tests/acceptance > $(RESULTS)/dryrun.txt 2>&1; \
		status=$$?; cat $(RESULTS)/dryrun.txt; test $$status -eq 0
	@if grep -q '\[ WARN \]' $(RESULTS)/dryrun.txt; then \
		echo "robot --dryrun printed warnings"; exit 1; fi

clean:
	docker compose down -v
	rm -rf $(RESULTS) .coverage .coverage.* .pytest_cache .ruff_cache
