# Listados, carga progresiva y scroll

Los listados de emergencias, convocatorias, ofertas, usuarios, organizaciones y
lotes publicados para ONG solicitan bloques de 20 registros. Al acercarse al
final del contenedor se consulta el siguiente bloque. El botón **Cargar más**
permite hacer lo mismo con teclado o sin `IntersectionObserver`. Un error al
cargar otra página conserva los registros anteriores y ofrece reintentar.

Los endpoints GET `/api/v1/emergencias`, `/convocatorias`, `/ofertas`, `/usuarios`,
`/organizaciones`, `/emergencias/{id}/lotes` y `/notificaciones` admiten:

- `limit`: entre 1 y 100 registros.
- `offset`: desplazamiento desde cero, siempre no negativo.

La respuesta sigue siendo un array. El frontend solicita 21 filas, muestra 20 y
usa la adicional para saber si hay otra página, avanzando el offset de 20 en 20.
El orden incluye un identificador como desempate. La autorización se aplica
antes del límite en SQL. Emergencias también admite `tiene_lotes` y `estado`,
aplicados en PostgreSQL antes de paginar. Las claves de caché separan páginas,
filtros y consultas completas; las mutaciones y los eventos invalidan sus listados.

Omitir `limit` conserva el contrato anterior para los selectores, formularios y
consumidores internos que necesitan la colección completa. En notificaciones se
conserva el resumen de las últimas 50 novedades para la campana, mientras que el
panel abierto consulta páginas y permite recorrer también las anteriores.

Inventario y catálogo nacionales, capacidades habilitadas, acreditaciones y
tablas del auditor renderizan bloques de 20 con el mismo scroll y botón. La API
nacional todavía entrega colecciones completas: este cambio reduce el DOM
inicial, pero no la descarga entre el backend local y la API nacional. Los
reportes mantienen el snapshot completo para gráficos y exportaciones; recorrer
sus tablas no vuelve a consultar Bonita.

Los formularios de lotes y ofertas usan scroll sin desmontar campos: se conservan
los valores y la validación de todos los ítems. Los selectores nativos conservan
sus opciones completas y el desplazamiento propio del navegador. No hay
virtualización: los bloques consultados permanecen disponibles al volver atrás.

Las páginas por offset reflejan el estado al momento de cada consulta. Una
inserción concurrente puede desplazar los resultados; el frontend deduplica por
ID. Actualizar o volver a entrar al listado recupera su estado vigente.
