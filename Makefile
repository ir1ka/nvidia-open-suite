BAR1_COMPONENT := $(if $(wildcard components/nvidia-bar1-p2p),components/nvidia-bar1-p2p,../nvidia-bar1-p2p)
.PHONY: check
check:
	PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
	PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s $(BAR1_COMPONENT)/tests -p 'test_source_copy.py'

.PHONY: check-source
check-source: check
	@test -n "$(SOURCE)" || { echo 'Set SOURCE to the prepared suite driver source' >&2; exit 2; }
	python3 $(BAR1_COMPONENT)/tests/check_driver.py --source "$(SOURCE)"
	python3 $(BAR1_COMPONENT)/tests/check_registry.py --source "$(SOURCE)"
	python3 $(BAR1_COMPONENT)/tests/check_lifetime.py --source "$(SOURCE)"
	python3 $(BAR1_COMPONENT)/tests/check_dynamic.py --source "$(SOURCE)"
	python3 tests/check_cmp.py --source "$(SOURCE)"

# Run in a disposable root container; synthetic PCI paths only.
.PHONY: check-gen2
check-gen2:
	python3 tests/gen2_runtime.py
