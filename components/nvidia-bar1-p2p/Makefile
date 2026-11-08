.PHONY: check check-source
check:
	PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
check-source: check
	@test -n "$(SOURCE)" || { echo 'Set SOURCE to the prepared Suite driver source' >&2; exit 2; }
	python3 tests/check_driver.py --source "$(SOURCE)"
	python3 tests/check_lifetime.py --source "$(SOURCE)"
	python3 tests/check_registry.py --source "$(SOURCE)"
