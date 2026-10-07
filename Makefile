.PHONY: run open test coverage eval verify verify-live benchmark benchmark-drb benchmark-lab benchmark-provider demo-seed docker-up docker-down

run:
	@open http://127.0.0.1:8765 2>/dev/null || true
	python app.py

open:
	@open http://127.0.0.1:8765

test:
	python -m compileall -q app.py tests
	python -m pytest -q

coverage:
	python -m pytest --cov=app --cov=flexresearch --cov-report=term-missing --cov-fail-under=80 -q

eval:
	python scripts/run_agent_eval.py

verify: test coverage eval

verify-live:
	python scripts/verify_live.py

benchmark:
	python scripts/benchmark_chat.py

benchmark-drb:
	python scripts/benchmark_deepresearch.py

benchmark-lab:
	python scripts/benchmark_lab.py

benchmark-provider:
	python scripts/benchmark_provider.py

demo-seed:
	python scripts/seed_showcase.py

docker-up:
	docker compose up --build

docker-down:
	docker compose down

