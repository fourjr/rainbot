#!/bin/bash

# rainbot Deployment Script
# This script helps deploy rainbot with various options

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check Python version
check_python() {
    if command_exists python3; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
        if python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
            print_success "Python $PYTHON_VERSION found"
            return 0
        else
            print_error "Python 3.8+ required, found $PYTHON_VERSION"
            return 1
        fi
    else
        print_error "Python 3 not found"
        return 1
    fi
}

# Function to check if virtual environment exists
check_venv() {
    if [ -d "venv" ] || [ -d ".venv" ]; then
        return 0
    else
        return 1
    fi
}

# Function to create virtual environment
create_venv() {
    print_status "Creating virtual environment..."
    python3 -m venv venv
    print_success "Virtual environment created"
}

# Function to activate virtual environment
activate_venv() {
    if [ -d "venv" ]; then
        source venv/bin/activate
    elif [ -d ".venv" ]; then
        source .venv/bin/activate
    else
        print_error "No virtual environment found"
        exit 1
    fi
}

# Function to install dependencies
install_deps() {
    print_status "Installing dependencies..."
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
        print_success "Dependencies installed"
    else
        print_error "requirements.txt not found"
        exit 1
    fi
}

# Function to check environment variables
check_env() {
    if [ ! -f ".env" ]; then
        print_warning ".env file not found"
        print_status "Creating .env template..."
        cat > .env << EOF
# Discord Bot Configuration
token=your_discord_bot_token_here
mongo=your_mongodb_connection_string
owners=your_discord_user_id

# Optional Settings
DEBUG=false
LOG_LEVEL=INFO
EOF
        print_success ".env template created"
        print_warning "Please edit .env file with your actual values"
        exit 1
    fi
    
    # Check if required variables are set
    if ! grep -q "token=" .env || grep -q "token=your_discord_bot_token_here" .env; then
        print_error "Discord token not configured in .env"
        exit 1
    fi
    
    if ! grep -q "mongo=" .env || grep -q "mongo=your_mongodb_connection_string" .env; then
        print_error "MongoDB connection string not configured in .env"
        exit 1
    fi
}

# Function to run the bot
run_bot() {
    print_status "Starting rainbot..."
    python bot.py
}

# Function to show logs
show_logs() {
    if [ -f "rainbot.log" ]; then
        tail -f rainbot.log
    else
        print_warning "No log file found"
    fi
}

# Function to show status
show_status() {
    if pgrep -f "python.*bot.py" > /dev/null; then
        print_success "rainbot is running"
        ps aux | grep "python.*bot.py" | grep -v grep
    else
        print_warning "rainbot is not running"
    fi
}

# Function to show help
show_help() {
    echo "rainbot Deployment Script"
    echo ""
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  install     Install dependencies and setup environment"
    echo "  run         Run the bot"
    echo "  logs        Show logs"
    echo "  status      Show status"
    echo "  update      Update the bot"
    echo "  help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 install"
    echo "  $0 run"
    echo "  $0 logs"
}

# Function to update the bot
update_bot() {
    print_status "Updating rainbot..."
    git pull origin main
    if check_venv; then
        activate_venv
        install_deps
    fi
    print_success "rainbot updated"
}

# Main script logic
case "${1:-help}" in
    install)
        print_status "Installing rainbot..."
        check_python
        if ! check_venv; then
            create_venv
        fi
        activate_venv
        install_deps
        check_env
        print_success "Installation complete!"
        print_status "Run '$0 run' to start the bot"
        ;;
    run)
        check_python
        if check_venv; then
            activate_venv
        fi
        check_env
        run_bot
        ;;
    logs)
        show_logs
        ;;
    status)
        show_status
        ;;
    update)
        update_bot
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac 