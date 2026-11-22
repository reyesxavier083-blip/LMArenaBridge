# LEYRA IA OMEGA — OpenRouter

## Estado de integración

El gateway de LEYRA ya implementa una interfaz de proveedor neutral compatible con la API de chat de OpenAI. Por ello, OpenRouter puede utilizarse como proveedor sin añadir un SDK específico.

## Configuración del servidor

Configura estas variables en el entorno privado del servidor:

```bash
LEYRA_UPSTREAM_BASE_URL=https://openrouter.ai/api/v1
LEYRA_UPSTREAM_API_KEY=<OPENROUTER_API_KEY>
LEYRA_UPSTREAM_TIMEOUT_SECONDS=90
LEYRA_GATEWAY_TOKEN=<TOKEN_PRIVADO_DE_LEYRA>
```

No guardes claves reales en el repositorio, en el frontend, en archivos APK ni en registros.

## Rutas de LEYRA

- `GET /leyra/connection/test`: verifica la conexión real consultando el catálogo de modelos del proveedor.
- `GET /leyra/v1/models`: devuelve los modelos disponibles.
- `POST /leyra/v1/chat/completions`: envía solicitudes de chat compatibles.

El cliente de LEYRA debe autenticarse ante el gateway con el token privado de LEYRA. El gateway utiliza la clave de OpenRouter exclusivamente en el servidor.

## Cabeceras opcionales de atribución

OpenRouter admite `HTTP-Referer` y `X-OpenRouter-Title` como cabeceras opcionales. La integración actual no necesita estas cabeceras para autenticarse ni para utilizar la API básica.

## Verificación

1. Configurar las variables en el servidor.
2. Reiniciar el servicio.
3. Ejecutar `GET /leyra/connection/test`.
4. Confirmar que devuelve `connection: connected`.
5. Consultar `GET /leyra/v1/models`.
6. Enviar una solicitud de prueba a `POST /leyra/v1/chat/completions` con un identificador de modelo devuelto por el catálogo.

Una prueba simulada no demuestra que la cuenta real esté conectada. La conexión solo se considera verificada después de una respuesta satisfactoria del servicio remoto con credenciales válidas.

## Seguridad y alcance

- Mantener HTTPS para el proveedor remoto.
- No devolver la clave de OpenRouter al cliente.
- No registrar cabeceras de autorización.
- No cambiar los módulos protegidos de Security & Privacy, Compliance Engine, Content Authenticity, Retention Manager, EFS Adapter, AI Gateway ni Audit & Monitoring.
- No cambiar la interfaz visual de la aplicación en esta integración.
