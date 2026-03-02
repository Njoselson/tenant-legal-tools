#!/bin/bash
# Deployment script for Tenant Legal Guidance on managed VPS
# Usage: ./deploy.sh [setup|update|backup|restore]

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="/opt/tenant_legal_guidance"
ENV_FILE="$PROJECT_DIR/.env"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [ "$EUID" -ne 0 ]; then 
        log_error "Please run as root or with sudo"
        exit 1
    fi
}

setup_server() {
    log_info "Setting up server environment..."
    
    # Update system
    log_info "Updating system packages..."
    apt update && apt upgrade -y
    
    # Install Docker
    if ! command -v docker &> /dev/null; then
        log_info "Installing Docker..."
        curl -fsSL https://get.docker.com -o get-docker.sh
        sh get-docker.sh
        rm get-docker.sh
    else
        log_info "Docker already installed"
    fi
    
    # Install Docker Compose
    if ! command -v docker compose &> /dev/null; then
        log_info "Installing Docker Compose..."
        apt install docker-compose-plugin -y
    else
        log_info "Docker Compose already installed"
    fi
    
    # Install other dependencies
    log_info "Installing additional packages..."
    apt install -y git nginx certbot python3-certbot-nginx
    
    # Enable Docker on boot
    systemctl enable docker
    systemctl start docker
    
    log_info "Server setup complete!"
}

setup_project() {
    log_info "Setting up project..."
    
    # Create project directory
    mkdir -p /opt
    cd /opt
    
    # Check if project already exists
    if [ -d "$PROJECT_DIR" ]; then
        log_warn "Project directory already exists at $PROJECT_DIR"
        read -p "Continue anyway? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        log_info "Cloning repository..."
        # Note: Update this URL with your actual repository
        git clone https://github.com/yourusername/tenant_legal_guidance.git
    fi
    
    cd "$PROJECT_DIR"
    
    # Create .env file if it doesn't exist
    if [ ! -f "$ENV_FILE" ]; then
        log_info "Creating .env file template..."
        cat > "$ENV_FILE" << EOF
# DeepSeek LLM API (REQUIRED)
DEEPSEEK_API_KEY=sk-your-key-here

# ArangoDB Configuration
ARANGO_HOST=http://arangodb:8529
ARANGO_DB_NAME=tenant_legal_kg
ARANGO_USERNAME=root
ARANGO_PASSWORD=$(openssl rand -base64 32)

# Qdrant Configuration
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=legal_chunks

# Embedding Model
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2

# Application Settings
LOG_LEVEL=INFO
DEBUG=false
EOF
        chmod 600 "$ENV_FILE"
        log_warn "Please edit $ENV_FILE and add your DEEPSEEK_API_KEY"
        log_warn "Generated random password for ArangoDB - save it securely!"
    else
        log_info ".env file already exists"
    fi
    
    log_info "Project setup complete!"
}

deploy_app() {
    log_info "Deploying application..."
    
    if [ ! -d "$PROJECT_DIR" ]; then
        log_error "Project directory not found at $PROJECT_DIR"
        log_error "Run 'setup' first or ensure project is at $PROJECT_DIR"
        exit 1
    fi
    
    cd "$PROJECT_DIR"
    
    # Check if .env exists
    if [ ! -f "$ENV_FILE" ]; then
        log_error ".env file not found. Please create it first."
        exit 1
    fi
    
    # Build and start
    log_info "Building Docker images..."
    docker compose build
    
    log_info "Starting services..."
    docker compose up -d
    
    log_info "Waiting for services to be ready..."
    sleep 10
    
    # Check health
    log_info "Checking application health..."
    if curl -f http://localhost:8000/api/health > /dev/null 2>&1; then
        log_info "Application is running!"
    else
        log_warn "Application may not be ready yet. Check logs with: docker compose logs"
    fi
    
    log_info "Deployment complete!"
}

update_app() {
    log_info "Updating application..."
    
    if [ ! -d "$PROJECT_DIR" ]; then
        log_error "Project directory not found"
        exit 1
    fi
    
    cd "$PROJECT_DIR"
    
    # Pull latest code
    if [ -d ".git" ]; then
        log_info "Pulling latest code..."
        git pull
    else
        log_warn "Not a git repository, skipping git pull"
    fi
    
    # Rebuild and restart
    log_info "Rebuilding and restarting services..."
    docker compose down
    docker compose build
    docker compose up -d
    
    log_info "Update complete!"
}

backup_data() {
    log_info "Creating backup..."
    
    BACKUP_DIR="/opt/backups/tenant-legal-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    
    cd "$PROJECT_DIR"
    
    # Backup ArangoDB
    log_info "Backing up ArangoDB..."
    ARANGO_PASSWORD=$(grep ARANGO_PASSWORD "$ENV_FILE" | cut -d '=' -f2)
    docker compose exec -T arangodb arangodump \
        --server.password "$ARANGO_PASSWORD" \
        --output-directory /tmp/arangodb-backup || log_warn "ArangoDB backup failed"
    
    docker compose cp arangodb:/tmp/arangodb-backup "$BACKUP_DIR/arangodb" || true
    
    # Backup Qdrant (Docker volume)
    log_info "Backing up Qdrant..."
    docker run --rm \
        -v tenant_legal_guidance_qdrant_data:/data \
        -v "$BACKUP_DIR":/backup \
        ubuntu tar czf /backup/qdrant-backup.tar.gz -C /data . || log_warn "Qdrant backup failed"
    
    # Backup .env (without sensitive data)
    log_info "Backing up configuration..."
    cp "$ENV_FILE" "$BACKUP_DIR/.env.backup" || true
    
    log_info "Backup created at: $BACKUP_DIR"
}

setup_nginx() {
    log_info "Setting up Nginx reverse proxy..."
    
    read -p "Enter your domain name (or press Enter to skip): " DOMAIN
    
    if [ -z "$DOMAIN" ]; then
        log_warn "Skipping Nginx setup. You can configure it manually later."
        return
    fi
    
    # Create Nginx config
    cat > /etc/nginx/sites-available/tenant-legal << EOF
server {
    listen 80;
    server_name $DOMAIN;

    proxy_read_timeout 300s;
    proxy_connect_timeout 75s;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
    }
}
EOF
    
    # Enable site
    ln -sf /etc/nginx/sites-available/tenant-legal /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    
    # Test and reload
    nginx -t && systemctl reload nginx
    
    log_info "Nginx configured for $DOMAIN"
    log_info "Run 'certbot --nginx -d $DOMAIN' to set up SSL"
}

setup_firewall() {
    log_info "Configuring firewall..."
    
    ufw allow 22/tcp   # SSH
    ufw allow 80/tcp   # HTTP
    ufw allow 443/tcp  # HTTPS
    
    # Enable firewall (non-interactive)
    ufw --force enable
    
    log_info "Firewall configured"
}

# Main script logic
case "${1:-deploy}" in
    setup)
        check_root
        setup_server
        setup_project
        setup_firewall
        log_info "Initial setup complete!"
        log_info "Next steps:"
        log_info "1. Edit $ENV_FILE and add your DEEPSEEK_API_KEY"
        log_info "2. Run: ./deploy.sh deploy"
        ;;
    deploy)
        check_root
        deploy_app
        setup_nginx
        ;;
    update)
        check_root
        update_app
        ;;
    backup)
        check_root
        backup_data
        ;;
    nginx)
        check_root
        setup_nginx
        ;;
    firewall)
        check_root
        setup_firewall
        ;;
    *)
        echo "Usage: $0 {setup|deploy|update|backup|nginx|firewall}"
        echo ""
        echo "Commands:"
        echo "  setup    - Initial server and project setup"
        echo "  deploy   - Deploy/start the application"
        echo "  update   - Update and restart the application"
        echo "  backup   - Create backup of data"
        echo "  nginx    - Configure Nginx reverse proxy"
        echo "  firewall - Configure firewall rules"
        exit 1
        ;;
esac

