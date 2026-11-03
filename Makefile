.PHONY: install run test docker clean

install:
	pip install -r requirements.txt

run:
	python run.py

test:
	pytest tests/ -v

docker:
	docker compose up --build

clean:
	rm -rf data/agentsearch.db .pytest_cache __pycache__ backend/__pycache__ backend/*/__pycache__
