# make up       Levanta MongoDB
# make samples  Regenera los Excel de muestra (samples/)
# make demo     Procesa los Excel de muestra
# make run      Procesa los Excel pendientes de INPUT_DIR
# make fresh    Borra la base y procesa todos los Excel desde cero
# make status   Muestra los resultados

CLI = uv run python -m app.cli

.DEFAULT_GOAL := status
.PHONY: up samples demo run fresh status

up:
	docker compose up -d

samples:
	@uv run python -m scripts.samples

demo:
	@$(CLI) run samples

run:
	@$(CLI) run

fresh:
	@$(CLI) run --reset

status:
	@$(CLI) status
