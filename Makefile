# make up       Levanta MongoDB
# make run      Procesa los Excel pendientes de la carpeta
# make fresh    Borra la base y procesa todos los Excel desde cero
# make status   Muestra los resultados

CLI = uv run python -m app.cli

.DEFAULT_GOAL := status
.PHONY: up run fresh status

up:
	docker compose up -d

run:
	@$(CLI) run

fresh:
	@$(CLI) run --reset

status:
	@$(CLI) status
