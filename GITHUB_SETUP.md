# Configuración de GitHub Actions para CI/CD

Este documento detalla las variables y secretos necesarios para configurar el flujo de trabajo de Integración y Despliegue Continuo (CI/CD) en GitHub.

## 1. Secretos de GitHub (Secrets)

Para que el workflow funcione, debes ir a tu repositorio en GitHub -> **Settings** -> **Secrets and variables** -> **Actions** -> **New repository secret** y añadir las siguientes variables:

| Nombre del Secreto | Descripción | Ejemplo |
|--------------------|-------------|---------|
| `DOCKER_USERNAME` | Tu nombre de usuario en Docker Hub. | `tu_usuario` |
| `DOCKER_PASSWORD` | Tu contraseña de Docker Hub o Access Token (recomendado). | `dckr_pat_...` |
| `KUBE_CONFIG` | El contenido de tu archivo `~/.kube/config` codificado en base64 o texto plano (GitHub lo encripta). **Importante:** La IP del servidor en este archivo debe ser pública o accesible desde internet, no `127.0.0.1` o IPs locales `192.168.x.x` si usas GitHub runners oficiales. | Ver abajo cómo obtenerlo |

### Cómo obtener `KUBE_CONFIG`

1. En tu servidor (donde corre k3s/k8s), obtén el archivo de configuración:
   ```bash
   cat ~/.kube/config
   # O si usas k3s y no lo has copiado:
   sudo cat /etc/rancher/k3s/k3s.yaml
   ```
2. **CRÍTICO:** Edita la línea `server: https://127.0.0.1:6443` y cambia `127.0.0.1` por la **IP Pública** o dominio de tu servidor.
3. Copia todo el contenido del archivo y pégalo en el secreto `KUBE_CONFIG`.

## 2. Funcionamiento del Workflow

El archivo `.github/workflows/ci-cd.yml` realiza los siguientes pasos automáticamente cada vez que haces un `git push` a la rama `main` o `master`:

1.  **Test:**
    *   Instala Python y las dependencias.
    *   Ejecuta `python -m unittest constraints_test.py` para asegurar que el código es correcto.

2.  **Build & Push:**
    *   Si los tests pasan, se loguea en Docker Hub.
    *   Construye la imagen Docker para arquitecturas **AMD64** (PC estándar) y **ARM64** (Raspberry Pi, Apple Silicon).
    *   Sube la imagen a Docker Hub con dos etiquetas: `latest` y `sha-<commit-hash>`.

3.  **Deploy:**
    *   Configura `kubectl` usando el secreto `KUBE_CONFIG`.
    *   Modifica el archivo `k8s/deployment.yaml` al vuelo para usar la imagen específica recién creada (versión `sha-...`).
    *   Aplica los manifiestos (`kubectl apply`) en tu cluster.
    *   Reinicia el despliegue para forzar la descarga de la nueva imagen.

## 3. Requisitos del Cluster

*   El cluster debe ser accesible desde Internet (puerto 6443 abierto) para que GitHub Actions pueda conectar.
*   Si tu cluster es casero (ej. Raspberry Pi en casa) y no tienes IP pública fija, podrías necesitar:
    *   Usar un túnel como **Cloudflare Tunnel** o **ngrok**.
    *   O configurar un **Self-hosted Runner** de GitHub en tu Raspberry Pi (opción más segura, no requiere abrir puertos).

### Opción Recomendada para Home Labs: Self-Hosted Runner

Si no quieres exponer tu API de Kubernetes a internet:

1.  Ve a GitHub -> Settings -> Actions -> Runners -> New self-hosted runner.
2.  Sigue las instrucciones para instalar el agente en tu Raspberry Pi/Servidor.
3.  Edita `.github/workflows/ci-cd.yml` y cambia `runs-on: ubuntu-latest` por `runs-on: self-hosted`.
4.  En este caso, el `KUBE_CONFIG` puede usar la IP local o `localhost`.
