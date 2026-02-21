#!/bin/bash

# Script de release con versionado para ArgoCD
# Uso: ./release.sh [patch|minor|major] "mensaje del commit"

set -e

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Colores adicionales
BLUE='\033[0;34m'

print_success() { echo -e "${BLUE}[SUCCESS]${NC} $1"; }

# Variables
IMAGE_NAME="quay-assignment-plan-or-tools"
DEPLOYMENT_FILE="k8s/deployment.yaml"
VERSION_FILE="VERSION"
ARGOCD_APP_NAME="quay-assignment-plan-or-tools"

# Leer versión actual
if [ ! -f "$VERSION_FILE" ]; then
    echo "1.0.0" > "$VERSION_FILE"
fi

CURRENT_VERSION=$(cat "$VERSION_FILE" | tr -d '
')
print_info "Versión actual: v$CURRENT_VERSION"

# Función para incrementar versión
increment_version() {
    local version=$1
    local type=$2

    IFS='.' read -r -a parts <<< "$version"
    local major="${parts[0]}"
    local minor="${parts[1]}"
    local patch="${parts[2]}"

    case "$type" in
        major)
            major=$((major + 1))
            minor=0
            patch=0
            ;;
        minor)
            minor=$((minor + 1))
            patch=0
            ;;
        patch)
            patch=$((patch + 1))
            ;;
        *)
            print_error "Tipo de versión inválido: $type"
            exit 1
            ;;
    esac

    echo "${major}.${minor}.${patch}"
}

# Verificar argumentos
VERSION_TYPE=${1:-patch}
COMMIT_MESSAGE=${2:-"Release"}

if [[ ! "$VERSION_TYPE" =~ ^(patch|minor|major)$ ]]; then
    print_error "Tipo de versión debe ser: patch, minor o major"
    echo ""
    echo "Uso: $0 [patch|minor|major] "mensaje del commit""
    echo ""
    echo "Versionado semántico (MAJOR.MINOR.PATCH):"
    echo "  patch  - Correcciones de bugs (1.0.0 -> 1.0.1)"
    echo "  minor  - Nueva funcionalidad compatible (1.0.0 -> 1.1.0)"
    echo "  major  - Cambios incompatibles (1.0.0 -> 2.0.0)"
    echo ""
    echo "Ejemplos:"
    echo "  $0 patch "Fix button alignment""
    echo "  $0 minor "Add dark mode feature""
    echo "  $0 major "Complete redesign""
    exit 1
fi

# Calcular nueva versión
NEW_VERSION=$(increment_version "$CURRENT_VERSION" "$VERSION_TYPE")
print_info "Nueva versión: v$NEW_VERSION"

# Verificar que no haya cambios sin commit
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
    print_warning "Tienes cambios sin commit."
    git status --short
    echo ""
    read -p "¿Continuar de todas formas? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_error "Operación cancelada"
        exit 1
    fi
fi

# Mostrar plan
echo ""
print_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
print_info "Plan de release:"
print_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  1. Actualizar VERSION: $CURRENT_VERSION -> $NEW_VERSION"
echo "  2. Actualizar deployment.yaml: ghcr.io/3kn4ls/${IMAGE_NAME}:v${NEW_VERSION}"
echo "  3. Commit y push a GitHub"
echo "  4. GitHub Actions: build multi-arch (~5 min)"
echo "  5. Push a GHCR (GitHub Container Registry)"
echo "  6. ArgoCD sync automático"
echo ""
read -p "¿Proceder? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_error "Operación cancelada"
    exit 1
fi

# 1. Actualizar archivo VERSION
print_info "Paso 1/3: Actualizando VERSION..."
echo "$NEW_VERSION" > "$VERSION_FILE"

# 2. Actualizar deployment.yaml
print_info "Paso 2/3: Actualizando deployment.yaml..."
sed -i "s|image: ghcr.io/3kn4ls/${IMAGE_NAME}:v.*|image: ghcr.io/3kn4ls/${IMAGE_NAME}:v${NEW_VERSION}|g" "$DEPLOYMENT_FILE"

# Verificar el cambio
if grep -q "image: ghcr.io/3kn4ls/${IMAGE_NAME}:v${NEW_VERSION}" "$DEPLOYMENT_FILE"; then
    print_info "✓ Deployment actualizado a v${NEW_VERSION}"
else
    print_error "Error al actualizar deployment.yaml"
    exit 1
fi

# 3. Commit y push
print_info "Paso 3/3: Haciendo commit y push a GitHub..."

git add "$VERSION_FILE" "$DEPLOYMENT_FILE"
git commit -m "release: v${NEW_VERSION} - ${COMMIT_MESSAGE}

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

git push origin main

if [ $? -eq 0 ]; then
    echo ""
    print_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    print_success "✅ Release v${NEW_VERSION} iniciado!"
    print_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    print_info "📦 Imagen: ghcr.io/3kn4ls/${IMAGE_NAME}:v${NEW_VERSION}"
    print_info "🔄 Commit: $(git rev-parse --short HEAD)"
    print_info "📝 Mensaje: ${COMMIT_MESSAGE}"
    echo ""
    print_warning "⏳ GitHub Actions está construyendo la imagen..."
    print_warning "   Esto tomará ~5-6 minutos"
    echo ""
    print_info "📊 Monitorear el progreso:"
    print_info "   GitHub Actions: https://github.com/3kn4ls/${IMAGE_NAME}/actions"
    print_info "   ArgoCD: https://northr3nd.duckdns.org/argocd"
    echo ""
    print_info "🔍 Ver estado local:"
    print_info "   kubectl get pods -n quay-solver -l app.kubernetes.io/name=quay-solver -w"
    echo ""
    print_success "🚀 ¡El despliegue se completará automáticamente!"
else
    print_error "Error al hacer push a Git"
    exit 1
fi
