.PHONY: install dev migrate zip
install:
	python -m venv .venv && . .venv/bin/activate && pip install -e .

dev:
	uvicorn app.main:app --reload --port 8000

migrate:
	alembic revision --autogenerate -m "baseline" && alembic upgrade head

zip:
	cd .. && zip -r ${PROJECT}.zip ${PROJECT}
