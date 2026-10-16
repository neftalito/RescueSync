# Administración del catálogo nacional

Un usuario local `ADMINISTRADOR` dispone de **Gestionar capacidades** en el
dashboard y de la pantalla `/catalogo-nacional`. Permite consultar capacidades
activas y crear una capacidad nueva con código, nombre, tipo de recurso, unidad
predefinida y admisión de fracciones. No ofrece altas, edición ni bajas de unidades.

Las unidades se cargan mediante la migración nacional `20261014_0002`, también
en producción. No dependen del seed demo. Cubren conteos, presentaciones de
suministros, alojamiento, volumen, masa, longitud, superficie, tiempo y servicios.
El detalle está en [el catálogo nacional](../../RescueSyncAPI/docs/catalogo-capacidades.md).

## Configuración y permisos

El navegador consume sólo la API local. El backend usa las credenciales de
servidor existentes `NACIONAL_CATALOGO_LOGIN` y `NACIONAL_CATALOGO_PASSWORD`.
`INTEGRACION` o `ADMIN_NACIONAL` permiten consultar; crear exige que la cuenta
nacional sea `ADMIN_NACIONAL`. Ser administrador local no cambia el rol nacional
de esa cuenta. No se envían contraseñas ni JWT nacionales al navegador.

Para las demostraciones, elegir el seed normal o el masivo en ambos proyectos.
Los dos seeds nacionales preparan el mismo administrador, por lo que las
credenciales del backend local no cambian al elegir una modalidad:

```dotenv
NACIONAL_CATALOGO_LOGIN=admin.nacional.demo@rescuesync.org
NACIONAL_CATALOGO_PASSWORD=admin-nacional-demo123
```

El seed masivo nacional permite consultar y crear capacidades sin ejecutar antes
el demo. Las contraseñas cambiadas se conservan y deben coincidir con la
configuración del backend. Tras editar `.env`, aplicar las variables con
`docker compose up -d --no-deps --force-recreate backend`.

Aplicar las migraciones de RescueSyncAPI antes de utilizar la pantalla nueva:

```bash
cd ../RescueSyncAPI
docker compose build api migrate
docker compose run --rm migrate
```

Para dar de alta una cuenta nacional propia se utiliza el bootstrap administrativo
descrito en [Certificaciones nacionales](../../RescueSyncAPI/docs/certificaciones.md).

## Endpoints del adaptador local

| Método y ruta | Permisos y efecto |
| --- | --- |
| `GET /api/v1/catalogo-nacional/capacidades` | Administrador local; consulta capacidades nacionales activas. |
| `GET /api/v1/catalogo-nacional/unidades` | Administrador local; consulta unidades predefinidas. |
| `POST /api/v1/catalogo-nacional/capacidades` | Administrador local, CSRF y cuenta nacional `ADMIN_NACIONAL`; crea una capacidad. |

El POST utiliza el contrato nacional en camelCase: `codigo`, `nombre`, `tipo`,
`unidad`, `admiteFracciones`. La unidad debe existir en la base nacional. Personal
y vehículos siempre usan cantidades enteras. Un código repetido produce `409`;
los errores conservan los datos del formulario. Tras crear se actualizan los
catálogos administrativos, de coordinación y de inventario de ONG.

El cliente compartido no reintenta un POST. Ante un timeout, actualizar el
catálogo y comprobar el código antes de repetir el alta.
