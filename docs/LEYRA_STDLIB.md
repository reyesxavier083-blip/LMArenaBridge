# LEYRA Gateway — modo estándar de Python

El lanzador `run_leyra.sh` utiliza `src.leyra_stdlib_server`, un servidor basado en `ThreadingHTTPServer`. Este modo no requiere instalar FastAPI, Uvicorn ni HTTPX.

## Configuración en Termux

Desde la carpeta del repositorio:

```bash
export LEYRA_UPSTREAM_BASE_URL="https://TU-PROVEEDOR/v1"
export LEYRA_UPSTREAM_API_KEY="TU_CLAVE_DEL_PROVEEDOR"
export LEYRA_GATEWAY_TOKEN="TU_TOKEN_PRIVADO"
export LEYRA_UPSTREAM_TIMEOUT_SECONDS="90"
chmod +x run_leyra.sh
./run_leyra.sh
```

En otra sesión de Termux:

```bash
curl -i http://127.0.0.1:8000/leyra/health
curl -i http://127.0.0.1:8000/leyra/connection/test \
  -H "Authorization: Bearer $LEYRA_GATEWAY_TOKEN"
```

Rutas compatibles:
- `GET /leyra/health`
- `GET /leyra/connection/test`
- `GET /leyra/v1/models`
- `POST /leyra/v1/chat/completions` (incluye respuesta en streaming SSE)

El gateway exige HTTPS para el proveedor; HTTP solo se permite cuando el proveedor está en localhost. El token del gateway es distinto de la clave del proveedor. No publiques ninguno de los dos.

## Alcance

Este modo implementa el transporte HTTP del gateway con módulos estándar de Python. No cambia el bridge principal de LMArena ni instala ni ejecuta automatización de navegador. El servidor local escucha en `127.0.0.1` de forma predeterminada.

Este servidor sencillo está pensado para pruebas y uso local. La documentación oficial de Python advierte que `http.server` no es una solución de producción; no lo expongas directamente a Internet. Para despliegues públicos, usa un servidor de producción detrás de HTTPS y controles de acceso adecuados.
