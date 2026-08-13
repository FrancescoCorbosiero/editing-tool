.PHONY: install test check demo preview clean

install:
	python -m venv .venv
	.venv/bin/pip install -r requirements.txt
	@echo "Attiva con: source .venv/bin/activate"

test:
	pytest -q

check:
	python -m vedit render projects/demo/timeline.yaml --dry-run

preview:
	python -m vedit render projects/demo/timeline.yaml --preview

demo:
	python -m vedit render projects/demo/timeline.yaml

clean:
	rm -rf output/*.mp4 proxies/ .pytest_cache __pycache__ vedit/__pycache__ tests/__pycache__
