# LEYRA IA — ejecución ligera en Termux

Esta modalidad inicia únicamente el gateway de LEYRA. No importa `src.main` ni instala Camoufox/Playwright, que no son necesarios para conectar LEYRA con un proveedor OpenAI-compatible.

## 1. Instalar dependencias

Desde la raíz del repositorio:

```bash
python -m pip install -r requirements-leyra.txt
```

## 2. Iniciar el gateway

```bash
bash run_leyra.sh
```

Por defecto escucha solo en `127.0.0.1:8000`. Mantén abierta esa sesión de Termux.

## 3. Comprobar que arrancó

En otra sesión de Termux:

```bash
curl -i http://127.0.0.1:8000/leyra/health
```

`status: needs_configuration` significa que el servidor arrancó, pero todavía no tiene proveedor y token configurados. No significa que la conexión externa esté lista.

## 4. Configurar el proveedor

Configura en el entorno del servidor `LEYRA_UPSTREAM_BASE_URL`, `LEYRA_UPSTREAM_API_KEY` y `LEYRA_GATEWAY_TOKEN`. Para OpenAI oficial, la URL base es `https://api.openai.com/v1`. La clave API debe crearla y administrarla el titular adulto autorizado de la cuenta; nunca la publiques en GitHub, el APK ni el chat. El token de LEYRA es otro secreto distinto.

Después reinicia el gateway y prueba la ruta autenticada `/leyra/connection/test`. Solo una respuesta HTTP 200 con `connection: connected` confirma que el proveedor respondió. La comprobación local `/health` no valida credenciales ni conectividad externa.

## 5. Probar modelos

```bash
curl -i http://127.0.0.1:8000/leyra/v1/models -H "Authorization: Bearer $LEYRA_GATEWAY_TOKEN"
```

Para el chat, usa `POST /leyra/v1/chat/completions` con JSON compatible con OpenAI y el mismo Bearer token de LEYRA.

## Solución del error `No module named uvicorn`

Instala las dependencias mínimas del paso 1. No hace falta instalar `camoufox` ni `playwright` para ejecutar este gateway independiente.
