# Despliegue del servicio de prioridad de RescueSync

**Requisitos.** Docker en ejecución, cuenta de Docker Hub, Minikube, kubectl y
curl. Para la prueba de carga, instalá [hey](https://github.com/rakyll/hey).
Ejecutá los comandos desde la raíz de RescueSync.

## 1. Imagen y despliegue

Creá un repositorio público `rescuesync-prioridad` en Docker Hub, reemplazá
`tu-usuario` por tu usuario y publicá la versión de la entrega.

```bash
IMAGEN=tu-usuario/rescuesync-prioridad:1.0.0
docker login
docker build -t "$IMAGEN" prioridad-emergencias
docker push "$IMAGEN"
```

Creá el clúster y aplicá los recursos. Metrics Server aporta la CPU que usa el
HPA. El Deployment ejecuta la imagen y el Service reúne a los pods disponibles.

```bash
minikube start --driver=docker
minikube addons enable metrics-server
sed "s|tu-usuario/rescuesync-prioridad:1.0.0|$IMAGEN|g" prioridad-emergencias/k8s.yaml |
  kubectl apply -f -
kubectl rollout status deployment/prioridad
minikube service prioridad --url
```

Para ensayar antes de publicar, después de crear el clúster cargá la imagen con
`minikube image load "$IMAGEN"` y aplicá el mismo manifiesto. Mantené abierta la
terminal de `minikube service` si queda ejecutando un túnel.

## 2. Verificación y escalado

En otra terminal, reemplazá `URL` por la dirección devuelta por Minikube.

```bash
URL=http://127.0.0.1:PUERTO
curl -fsS "$URL/health"
curl -fsS "$URL/prioridades" -H 'Content-Type: application/json' \
  -d '{"gravedad":"ALTA","zona":"SUR"}'
kubectl top pods
kubectl get hpa prioridad -w
```

La respuesta esperada es `{"prioridad":7}`. Esperá a que el HPA muestre un
porcentaje de CPU. En otra terminal, repetí la asignación de `URL` y ejecutá:

```bash
hey -z 2m -c 50 -m POST -T application/json \
  -d '{"gravedad":"ALTA","zona":"SUR"}' "$URL/prioridades"
```

Observá el aumento de réplicas bajo carga y el regreso a una cuando baje la CPU.
El HPA tiene un mínimo de 1, un máximo de 5 y un objetivo de CPU del 60 % sobre
los 50m solicitados por pod. La ventana de estabilización del descenso es de
60 segundos. El regreso a una réplica puede tomar varios minutos.

## 3. Alta municipal

Con `docker compose up --build`, el backend usa el priorizador de Compose.
Para integrarlo con un clúster, configurá `PRIORIDAD_BASE_URL` con la URL
accesible desde el backend y recreá ese servicio. Para una instalación pública,
publicá una URL HTTPS mediante el balanceador o Ingress del clúster.

Como operador municipal, elegí gravedad y zona, pulsá **Consultar prioridad** y
después **Registrar emergencia**. El ajuste usa el catálogo de demostración
`NORTE` (+0), `CENTRO` (+1) y `SUR` (+2) sobre las bases 1, 3, 5 y 8 para
`BAJA`, `MEDIA`, `ALTA` y `CRITICA`, respectivamente.
