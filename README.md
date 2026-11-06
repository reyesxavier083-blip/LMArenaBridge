# LMArenaBridge

LMArenaBridge es un proyecto Python que ofrece dos servicios diferenciados:

1. **Bridge de LM Arena:** expone una API compatible con OpenAI para interactuar con los flujos de LM Arena.
2. **Gateway independiente de LEYRA IA:** reenvía solicitudes a un proveedor externo que ofrezca una API compatible con OpenAI. Este gateway no depende del navegador ni de la sesión de LM Arena.

> **Importante:** el gateway de LEYRA no conecta automáticamente con LM Arena. Para que funcione, debes configurar la URL HTTPS y las credenciales de un proveedor compatible. La conexión se comprueba realmente consultando su endpoint `/models`.

## Requisitos

- Python 3.10 o superior (el repositorio fija Python 3.12.10).
- pip.
- Conexión a internet para instalar dependencias y acceder al proveedor.
- Para el bridge principal: dependencias de navegador de Playwright/Camoufox cuando el transporte elegido las requiera.
- Para LEYRA independiente: solamente FastAPI, Uvicorn y HTTPX.

## Instalación

Clona el repositorio:

```bash
git clone https://github.com/reyesxavier083-blip/LMArenaBridge.git
cd LMArenaBridge
```

### Bridge principal de LM Arena

Instala sus dependencias:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

También puedes instalar las herramientas de desarrollo:

```bash
python -m pip install -e ".[dev]"
```

Si vas a utilizar Playwright y necesitas instalar sus navegadores:

```bash
python -m playwright install
```

Inicia el servidor:

```bash
python -m src.main
```

Por defecto escucha únicamente en `127.0.0.1:8000`. Las variables `HOST` y `PORT` permiten cambiar explícitamente la dirección y el puerto; por ejemplo, `HOST=127.0.0.1 PORT=8001 python -m src.main`.

- Panel: `http://127.0.0.1:8000/dashboard`
- Inicio de sesión: `http://127.0.0.1:8000/login`
- API principal: `http://127.0.0.1:8000/api/v1`
- Documentación FastAPI: `http://127.0.0.1:8000/docs`

### Gateway independiente de LEYRA IA

Este modo es más ligero y no instala Camoufox ni Playwright.

Instala únicamente sus dependencias:

```bash
python -m pip install -r requirements-leyra.txt
```

Configura las variables de entorno antes de iniciar el servidor. Ejemplo para Linux, macOS o Termux:

```bash
export LEYRA_UPSTREAM_BASE_URL="https://TU-PROVEEDOR/v1"
export LEYRA_UPSTREAM_API_KEY="TU_CLAVE_DEL_PROVEEDOR"
export LEYRA_GATEWAY_TOKEN="CREA_UN_TOKEN_PRIVADO"
export LEYRA_UPSTREAM_TIMEOUT_SECONDS="90"
```

- `LEYRA_UPSTREAM_BASE_URL`: URL base de la API compatible con OpenAI. Debe usar HTTPS; HTTP solo se permite para localhost.
- `LEYRA_UPSTREAM_API_KEY`: clave del proveedor. Déjala vacía únicamente si el proveedor no requiere autenticación.
- `LEYRA_GATEWAY_TOKEN`: token privado que utilizará tu cliente para autenticarse ante LEYRA.
- `LEYRA_UPSTREAM_TIMEOUT_SECONDS`: tiempo de espera entre 5 y 300 segundos.

El archivo `.env.example` es una plantilla: **el gateway no carga automáticamente archivos .env**. Exporta las variables en la terminal o configura las variables de entorno en tu plataforma de despliegue. Nunca publiques claves ni tokens.

Inicia el gateway en Termux:

```bash
chmod +x run_leyra.sh
./run_leyra.sh
```

En otros entornos también puedes iniciarlo directamente:

```bash
python -m uvicorn src.leyra_gateway:app --host 127.0.0.1 --port 8000
```

Si el puerto 8000 está ocupado, cambia `PORT` al ejecutar el script:

```bash
PORT=8001 ./run_leyra.sh
```

#### Comprobar la conexión de LEYRA

En otra terminal, usa el mismo token configurado en `LEYRA_GATEWAY_TOKEN`:

```bash
curl -i http://127.0.0.1:8000/leyra/health
```

La ruta de salud no requiere autenticación. Para probar la conexión real con el proveedor:

```bash
curl -i http://127.0.0.1:8000/leyra/connection/test \
  -H "Authorization: Bearer TU_TOKEN_LEYRA"
```

Una conexión correcta devuelve HTTP 200 y `"connection":"connected"`. Si devuelve 502, revisa la URL del proveedor, su clave y que su endpoint `/models` esté disponible. Un HTTP 503 indica que falta configuración o que algún valor no es válido.

Rutas disponibles:

| Método | Ruta | Función |
|---|---|---|
| GET | `/leyra/health` | Estado básico del gateway |
| GET | `/leyra/connection/test` | Prueba autenticada contra el proveedor |
| GET | `/leyra/v1/models` | Lista modelos del proveedor |
| POST | `/leyra/v1/chat/completions` | Envía conversaciones; admite streaming |

#### Usar LEYRA desde un cliente OpenAI-compatible

Configura el cliente con la URL base y el token del gateway (no confundas este token con la clave del proveedor):

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8000/leyra/v1",
    api_key="TU_TOKEN_LEYRA",
)

response = client.chat.completions.create(
    model="NOMBRE_DEL_MODELO",
    messages=[{"role": "user", "content": "Hola"}],
)

print(response.choices[0].message.content)
```

El paquete `openai` se instala por separado si vas a ejecutar ese ejemplo:

```bash
python -m pip install openai
```

### Ejecutar ambos servicios

El servidor principal importa y monta también las rutas del gateway LEYRA bajo el prefijo `/leyra`. Por tanto, si ejecutas `python -m src.main`, puedes usar esas rutas en el mismo puerto, siempre que hayas instalado las dependencias del proyecto y configurado las variables de LEYRA. No inicies simultáneamente ambos servidores en el mismo puerto.

## Configuración y seguridad

- Mantén los servicios ligados a `127.0.0.1` mientras haces pruebas locales.
- No expongas el gateway directamente a internet sin HTTPS, control de acceso y una configuración de despliegue segura.
- No compartas `LEYRA_GATEWAY_TOKEN`, `LEYRA_UPSTREAM_API_KEY` ni archivos `.env`.
- El gateway valida el token Bearer del cliente y utiliza por separado la credencial del proveedor.
- El gateway limita el cuerpo de cada solicitud a 2 MiB y a 100 mensajes.
- El gateway LEYRA no resuelve desafíos, no extrae cookies y no automatiza sesiones de terceros.

## Pruebas

Instala las dependencias de desarrollo y ejecuta:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

Para ejecutar solamente las pruebas del gateway LEYRA:

```bash
python -m pytest tests/test_leyra_gateway.py -v
```

## Estructura principal

```text
.
├── src/
│   ├── main.py              # Aplicación principal de LM Arena
│   ├── leyra_gateway.py     # Gateway independiente y router de LEYRA
│   ├── auth.py              # Autenticación del bridge principal
│   ├── browser_utils.py     # Utilidades de navegador
│   ├── config.py            # Configuración del bridge
│   ├── constants.py         # Constantes
│   ├── recaptcha.py         # Integración de verificación del bridge
│   ├── state.py             # Estado compartido
│   ├── transport.py         # Transportes del bridge
│   └── vision_solver.py     # Integración opcional de visión
├── tests/                   # Pruebas automatizadas
├── requirements.txt         # Dependencias del bridge principal
├── requirements-leyra.txt   # Dependencias mínimas de LEYRA
├── run_leyra.sh             # Lanzador de LEYRA para Termux/Linux
├── .env.example             # Plantilla de variables de entorno
└── pyproject.toml           # Metadata y herramientas de desarrollo
```

## Licencia

Distribuido bajo la licencia MIT. Consulta [LICENSE](LICENSE).

## Referencias

- [Repositorio](https://github.com/reyesxavier083-blip/LMArenaBridge)
- [Incidencias](https://github.com/reyesxavier083-blip/LMArenaBridge/issues)
- [Historial de cambios](https://github.com/reyesxavier083-blip/LMArenaBridge/commits/main)


### Gateway LEYRA sin dependencias externas

Si estás en Termux y no tienes Uvicorn instalado, el lanzador `./run_leyra.sh` ya utiliza el servidor de la biblioteca estándar de Python. No necesitas instalar FastAPI, Uvicorn ni HTTPX para este modo. Consulta [docs/LEYRA_STDLIB.md](docs/LEYRA_STDLIB.md) para la configuración y las pruebas. El modo principal de LMArena conserva sus dependencias habituales.
