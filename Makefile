# make up       Levanta MongoDB
# make samples  Regenera los Excel de muestra (samples/)
# make demo     Procesa los Excel de muestra
# make run      Procesa los Excel pendientes de INPUT_DIR (deja el reporte en output/confidencial)
# make fresh    Borra la base y procesa todos los Excel desde cero
# make remap    Vuelve a mapear con IA solo las hojas pendientes
# make requote  Recalcula cotizaciones y reportes con los mapas guardados (sin IA)
# make status   Muestra los resultados

CLI = uv run python -m app.cli

.DEFAULT_GOAL := status
.PHONY: up samples demo run fresh remap requote status

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

remap:
	@$(CLI) run --from map

requote:
	@$(CLI) run --from quotes

status:
	@$(CLI) status
