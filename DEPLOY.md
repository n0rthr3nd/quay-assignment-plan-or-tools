# Guia de Despliegue - k3s en Raspberry Pi 5 (ARM64)

## Requisitos previos

| Componente | Detalle |
|---|---|
| Hardware | Raspberry Pi 5 (4GB min, 8GB recomendado) |
| OS | Raspberry Pi OS 64-bit (Bookworm) o Ubuntu Server 24.04 ARM64 |
| k3s | v1.28+ |
| Almacenamiento | microSD de 32GB+ o SSD NVMe via HAT (recomendado) |
| Red | IP fija en la red local |

## 1. Instalar k3s

```bash
# Instalar k3s (nodo unico, incluye Traefik + local-path-provisioner)
curl -sfL https://get.k3s.io | sh -

# Verificar instalacion
sudo k3s kubectl get nodes
# Deberia mostrar el nodo con STATUS Ready

# Configurar kubectl para tu usuario
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $(id -u):$(id -g) ~/.kube/config
export KUBECONFIG=~/.kube/config

# Verificar
kubectl get nodes
```

## 2. Construir la imagen Docker ARM64

### Opcion A: Construir directamente en la RPi5

```bash
# Clonar el repositorio en la RPi5
git clone <url-del-repositorio> quay-solver
cd quay-solver

# Construir imagen (ya es ARM64 nativo al estar en la RPi5)
sudo docker build -t quay-solver:latest .

# Importar al registro interno de k3s
sudo docker save quay-solver:latest | sudo k3s ctr images import -
```

### Opcion B: Construir en otra maquina con buildx (cross-compile)

```bash
# Desde tu PC/Mac (x86 o Apple Silicon)
docker buildx create --use --name rpibuilder
docker buildx build --platform linux/arm64 -t quay-solver:latest --load .

# Exportar y copiar a la RPi5
docker save quay-solver:latest -o quay-solver-arm64.tar
scp quay-solver-arm64.tar pi@<IP-RPI5>:~/

# En la RPi5, importar
ssh pi@<IP-RPI5>
sudo k3s ctr images import ~/quay-solver-arm64.tar
```

### Opcion C: Usar un registro privado

Si tienes un registry local (p.ej. en la misma RPi5 o en tu red):

```bash
# Levantar registry local (ejecutar una sola vez)
sudo docker run -d -p 5000:5000 --restart=always --name registry registry:2

# Construir y subir
sudo docker build -t localhost:5000/quay-solver:latest .
sudo docker push localhost:5000/quay-solver:latest
```

Si usas registry local, editar `k8s/deployment.yaml` y cambiar la imagen:

```yaml
image: localhost:5000/quay-solver:latest
```

Y crear el archivo `/etc/rancher/k3s/registries.yaml`:

```yaml
mirrors:
  "localhost:5000":
    endpoint:
      - "http://localhost:5000"
```

Reiniciar k3s: `sudo systemctl restart k3s`

## 3. Desplegar en k3s

```bash
# Desde el directorio del repositorio
cd quay-solver

# Aplicar manifiestos en orden
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml

# Verificar que todo esta corriendo
kubectl -n quay-solver get all
```

Salida esperada:

```
NAME                              READY   STATUS    RESTARTS   AGE
pod/quay-solver-xxxxxxxxx-xxxxx   1/1     Running   0          30s

NAME                  TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)   AGE
service/quay-solver   ClusterIP   10.43.xxx.xx   <none>        80/TCP    30s

NAME                          READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/quay-solver   1/1     1            1           30s
```

## 4. Acceder a la aplicacion

### Via Ingress (con dominio)

Agregar al archivo `/etc/hosts` de tu PC cliente:

```
<IP-DE-LA-RPI5>    quay.local
```

Abrir en el navegador: `http://quay.local`

### Via Port-Forward (acceso rapido sin configurar DNS)

```bash
kubectl -n quay-solver port-forward svc/quay-solver 8080:80
```

Abrir en el navegador: `http://localhost:8080`

### Via NodePort (alternativa sin Ingress)

Cambiar el tipo de servicio en `k8s/service.yaml`:

```yaml
spec:
  type: NodePort
  ports:
    - port: 80
      targetPort: http
      nodePort: 30500     # Puerto fijo en el rango 30000-32767
```

Aplicar: `kubectl apply -f k8s/service.yaml`

Acceder: `http://<IP-RPI5>:30500`

## 5. Operaciones habituales

### Ver logs

```bash
kubectl -n quay-solver logs -f deployment/quay-solver
```

### Reiniciar la aplicacion

```bash
kubectl -n quay-solver rollout restart deployment/quay-solver
```

### Actualizar la imagen

```bash
# Construir nueva imagen
sudo docker build -t quay-solver:latest .
sudo docker save quay-solver:latest | sudo k3s ctr images import -

# Forzar redespliegue
kubectl -n quay-solver rollout restart deployment/quay-solver
```

### Ver estado del PVC

```bash
kubectl -n quay-solver get pvc
kubectl -n quay-solver describe pvc quay-solver-data
```

### Eliminar todo

```bash
kubectl delete namespace quay-solver
```

## 6. Consideraciones para Raspberry Pi 5

### Memoria

El solver CP-SAT puede consumir bastante RAM con problemas grandes.
El deployment esta configurado con:
- **Request**: 512Mi (lo que k3s reserva)
- **Limit**: 2Gi (maximo que puede usar)

En una RPi5 de **4GB**, dejar al menos 1GB para el sistema.
En una RPi5 de **8GB**, puedes subir el limite a 4Gi editando `k8s/deployment.yaml`:

```yaml
resources:
  limits:
    memory: 4Gi
```

### CPU

El solver usa multiples hilos (8 workers por defecto). La RPi5 tiene 4 cores
Cortex-A76 a 2.4GHz. El deployment limita a 3 CPUs para dejar margen al sistema.

Para problemas grandes (>15 buques), considerar aumentar el tiempo limite del
solver desde la interfaz web (pestaña "Solver").

### Almacenamiento

Se recomienda usar un **SSD NVMe** via HAT M.2 en lugar de microSD:
- Mayor velocidad de I/O para las imagenes PNG generadas
- Mayor durabilidad (las microSD se degradan con escrituras frecuentes)
- El PVC `local-path` almacena datos en `/var/lib/rancher/k3s/storage/`

### Temperatura

El solver es CPU-intensivo. Asegurar refrigeracion adecuada:
- Disipador oficial de la RPi5 o cooler activo
- Monitorear con: `vcgencmd measure_temp`

## 7. Troubleshooting

### El pod queda en ImagePullBackOff

La imagen no esta disponible. Verificar:

```bash
sudo k3s ctr images list | grep quay-solver
```

Si no aparece, importarla de nuevo (ver paso 2).

### El pod queda en Pending

Verificar que el PVC esta bound:

```bash
kubectl -n quay-solver get pvc
```

Si esta en `Pending`, verificar que local-path-provisioner esta corriendo:

```bash
kubectl -n kube-system get pods | grep local-path
```

### El solver tarda demasiado

- Reducir el tiempo limite desde la web (pestaña "Solver")
- Reducir la cantidad de buques o gruas
- En problemas grandes, el solver devolvera la mejor solucion FEASIBLE
  encontrada dentro del limite de tiempo (no necesariamente OPTIMAL)

### OOMKilled

El pod se queda sin memoria. Reducir el tamaño del problema o aumentar
el limite en `k8s/deployment.yaml`:

```bash
kubectl -n quay-solver describe pod <nombre-del-pod> | grep -A5 "Last State"
```
