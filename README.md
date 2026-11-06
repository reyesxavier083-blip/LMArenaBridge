# LMArenaBridge

LMArenaBridge es un puente en Python para exponer una API compatible con OpenAI sobre modelos disponibles en LM Arena (`arena.ai`), manteniendo un comportamiento similar a `POST /api/v1/chat/completions`.

El proyecto está pensado para servir como capa intermedia entre clientes compatibles con OpenAI y la infraestructura interna de LM Arena, incluyendo manejo de autenticación, rotación de tokens y resolución de desafíos de Cloudflare/reCAPTCHA mediante automatización de navegador.

## Características

- Endpoint compatible con OpenAI: `POST /api/v1/chat/completions`
- Soporte para streaming de respuestas
- Proxy de requests a LM Arena con navegador automatizado
- Manejo de desafíos Cloudflare / Turnstile / reCAPTCHA
- Rotación de tokens de autenticación
- Detección y selección de transporte dinámico:
  - HTTP directo con `httpx`
  - Fetch vía Chrome/Playwright
  - Fetch vía Camoufox
  - Proxy usuarioscript para escenarios con autenticación limitada
- Compatibilidad con modelos y flujos de prueba automatizados

## Requisitos

- Python 3.10+ (el proyecto recomienda Python 3.12)
- `pip` y `virtualenv` / `venv`
- Navegadores compatibles con Playwright / Camoufox para automatización de navegador

## Instalación

Clona el repositorio:

```bash
git clone https://github.com/reyesxavier083-blip/LMArenaBridge.git
cd LMArenaBridge
```

Crea un entorno virtual e instala dependencias:

```bash
python -m venv .venv
source .venv/bin/activate  # En Windows usa: .venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt
```

Opcionalmente, si quieres instalar el paquete en modo editable con dependencias de desarrollo:

```bash
pip install -e ".[dev]"
```

Si usas Playwright y necesitas los navegadores instalados:

```bash
python -m playwright install
```

## Ejecución

Inicia el servidor:

```bash
python -m src.main
```

El servicio levanta la API FastAPI y queda listo para recibir peticiones OpenAI-like.

## Uso rápido

### Curl

```bash
curl -X POST "http://localhost:8000/api/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default",
    "messages": [
      {"role": "user", "content": "Hola, dime algo sobre LM Arena."}
    ],
    "stream": false
  }'
```

### Cliente compatible con OpenAI

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/api/v1",
    api_key="dummy-key",
)

response = client.chat.completions.create(
    model="default",
    messages=[{"role": "user", "content": "¿Cómo va todo?"}],
)

print(response.choices[0].message.content)
```

## Arquitectura

La estructura principal del proyecto es la siguiente:

```text
src/
├── main.py              # Aplicación FastAPI, rutas, streaming y lifecycle
├── constants.py         # Configuración, URLs, selectores, timeouts y constantes
├── config.py            # Carga/guardado de configuración y modelos
├── state.py             # Estado compartido en memoria
├── browser_utils.py     # Utilidades de navegador y Playwright
├── auth.py              # Gestión de tokens de autenticación
├── recaptcha.py         # Generación de tokens reCAPTCHA
├── transport.py         # Transportes HTTP/browser y streaming
└── ...
```

El proyecto implementa varios transportes para adaptarse a distintos escenarios de acceso a LM Arena:

1. HTTP directo con `httpx`
2. Fetch vía navegador con Chrome/Edge y Playwright
3. Fetch vía Camoufox
4. Proxy de userscript para long polling

## Modo de desarrollo y pruebas

Se incluye una configuración de pytest y comandos útiles:

```bash
# Ejecutar todas las pruebas
python -m pytest tests/

# Ejecutar un archivo individual
python -m pytest tests/test_stream_403_recaptcha_retries.py -v

# Ejecutar una prueba concreta
python -m pytest tests/test_stream_403_recaptcha_retries.py::TestStream403RecaptchaRetries::test_stream_403_recaptcha_validation_failed_retries_with_fresh_token -v

# Comprobación de sintaxis
python -c "import ast; ast.parse(open('src/main.py', encoding='utf-8').read()); print('OK')"
```

## Consideraciones importantes

- El proyecto usa automatización de navegador para sortear desafíos de verificación que pueden bloquear acceso directo a LM Arena.
- Los tokens de autenticación se gestionan con rotación y actualización periódica.
- En algunos escenarios puede requerirse navegador local instalado y/o credenciales/estado de sesión válidos para acceder a la plataforma.
- El servicio está orientado a entornos de desarrollo o despliegue controlado, no como una solución pública sin restricciones de acceso.

## Seguridad y uso responsable

Este proyecto interactúa con servicios externos y automatiza navegación web. Debe usarse conforme a:

- las políticas de uso del servicio destino,
- los términos de servicio de LM Arena,
- las licencias y restricciones del entorno donde se despliegue.

No se recomienda exponer este proxy en internet sin revisar la compatibilidad, el cumplimiento legal y la seguridad de la configuración.

## Licencia

Este proyecto se distribuye bajo la licencia MIT. Consulta el archivo `LICENSE` para más detalles.

## Agradecimientos y contexto

LMArenaBridge nace como una capa de integración para permitir acceso desde clientes compatibles con OpenAI a modelos disponibles en LM Arena, especialmente cuando la plataforma exige mecanismos adicionales de verificación y autenticación que no están expuestos por una API pública estándar.

---

Si quieres, puedo convertir este README a una versión más orientada a:

- GitHub con más badges y estructura comercial,
- documentación técnica más detallada para desarrolladores,
- versión en inglés,
- o una versión enfocada en uso con OpenAI SDK y Docker.

