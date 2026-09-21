# data/

Lo escribe el bot en cada corrida de GitHub Actions. No se edita a mano.

- `vacantes.csv`: registro de todo lo visto, pase o no el filtro. El esquema está en `docs/esquema.md`.
- `estado.json`: estado del bot (último mensaje de Telegram leído, fecha del último resumen, salud de cada fuente).

Para analizarlo: `pandas.read_csv("data/vacantes.csv", dtype=str)`. Con `dtype=str` pandas no convierte los ids a números.
