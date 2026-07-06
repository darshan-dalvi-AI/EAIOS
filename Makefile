.PHONY: dev backend frontend seed test up down

# Run backend + frontend locally (two terminals recommended)
backend:
	cd backend && uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

seed:
	cd backend && python -m app.seed

test:
	cd backend && pytest -q

up:
	docker compose up --build -d

down:
	docker compose down
