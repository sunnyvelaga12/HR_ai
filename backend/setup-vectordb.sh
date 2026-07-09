#!/bin/bash
# Quick Start Guide for Vector Database Setup
# Run this script to validate and initialize the vector database

set -e

echo "=================================="
echo "HR AI Vector Database Setup"
echo "=================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found${NC}"
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo -e "${YELLOW}✓ .env created. Please update it with your credentials.${NC}"
    echo ""
fi

# Check for required environment variables
echo "Checking environment configuration..."

check_env_var() {
    if grep -q "^$1=" .env && ! grep -q "^$1=YOUR_\|^$1=your-\|^$1=$" .env; then
        echo -e "${GREEN}✓ $1 configured${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠️  $1 not configured${NC}"
        return 1
    fi
}

echo ""
echo "Configuration Status:"
check_env_var "PINECONE_API_KEY" || echo "  → Set your Pinecone API key in .env"
check_env_var "GEMINI_API_KEY" || echo "  → Set your Gemini API key in .env"
check_env_var "AI_PROVIDER" || echo "  → Set AI_PROVIDER (google_genai or groq)"

echo ""
echo "Installing Python dependencies..."
pip install -q -r requirements.txt

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Dependencies installed successfully${NC}"
else
    echo -e "${RED}✗ Failed to install dependencies${NC}"
    exit 1
fi

echo ""
echo "=================================="
echo -e "${GREEN}✓ Setup Complete!${NC}"
echo "=================================="
echo ""
echo "Next steps:"
echo "1. Update your .env file with Pinecone credentials:"
echo "   - Get API key from https://www.pinecone.io"
echo "   - Set PINECONE_API_KEY in .env"
echo ""
echo "2. Start the backend server:"
echo "   python -m uvicorn app.main:app --reload"
echo ""
echo "3. Ingest policies (in another terminal):"
echo "   curl -X POST http://localhost:8000/api/v1/vectordb/ingest/policies \\"
echo "     -H 'Authorization: Bearer YOUR_JWT_TOKEN' \\"
echo "     -H 'Content-Type: application/json'"
echo ""
echo "4. Test search endpoint:"
echo "   curl 'http://localhost:8000/api/v1/vectordb/policies/search?query=leave'"
echo ""
echo "5. View API documentation:"
echo "   http://localhost:8000/docs"
echo ""
echo "For detailed setup guide, see: VECTOR_DB_SETUP.md"
echo ""
