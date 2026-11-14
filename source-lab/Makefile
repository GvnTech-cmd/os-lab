PYTHON ?= python3
.PHONY: help preflight doctor setup status test
help:
	$(PYTHON) run.py --help
preflight doctor:
	$(PYTHON) run.py doctor
setup:
	$(PYTHON) run.py setup
status:
	$(PYTHON) run.py status
test:
	cd engine && $(PYTHON) -m pytest -q
