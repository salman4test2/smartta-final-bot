# 🔧 Environment Configuration Guide

## Environment Variables

Create a `.env` file in the root directory with the following variables:

### Required Variables

```bash
# Database Configuration
DATABASE_URL=postgresql://user:password@host:port/database
# For local development: DATABASE_URL=sqlite+aiosqlite:///./data/watemp.db

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini

# LLM Configuration
LLM_TEMPERATURE=0.2

# Application Configuration
CONFIG_PATH=./config/whatsapp.yaml
```

### Environment-Specific Variables

```bash
# Environment setting (affects CORS and other behaviors)
ENVIRONMENT=development  # Options: development, staging, production

# CORS Configuration (Production only)
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# Optional: Override default server settings
HOST=0.0.0.0
PORT=8000
```

## Environment Configurations

### Development
- **ENVIRONMENT=development**
- CORS allows all origins (`["*"]`)
- More verbose logging
- Local database recommended

### Staging  
- **ENVIRONMENT=staging**
- CORS allows localhost + staging domains
- Intermediate security settings
- Can use production database or separate staging DB

### Production
- **ENVIRONMENT=production** 
- CORS restricted to specified origins only
- Enhanced security
- Production database required
- All secrets properly configured

## CORS Security

The app automatically configures CORS based on the environment:

- **Development**: `allow_origins=["*"]` for easy development
- **Staging**: Predefined list including localhost and staging domains
- **Production**: Only origins specified in `CORS_ORIGINS` environment variable

## Database Setup

### PostgreSQL (Recommended for Production)
```bash
DATABASE_URL=postgresql://username:password@host:port/database_name
```

### SQLite (Development Only)
```bash
DATABASE_URL=sqlite+aiosqlite:///./data/watemp.db
```

## Security Checklist

- [ ] Set `ENVIRONMENT=production` in production
- [ ] Configure `CORS_ORIGINS` with your actual domain(s)
- [ ] Use strong database passwords
- [ ] Keep `OPENAI_API_KEY` secure and rotated
- [ ] Ensure `.env` file is not committed to version control
- [ ] Use HTTPS in production
- [ ] Enable database SSL in production

## Quick Start

1. Copy `.env.example` to `.env` (if provided) or create new `.env`
2. Set your `OPENAI_API_KEY`
3. Configure your `DATABASE_URL`
4. Set `ENVIRONMENT` appropriately
5. Run `uvicorn app.main:app --reload`

## Production Deployment

For production deployment:

1. Set `ENVIRONMENT=production`
2. Configure `CORS_ORIGINS` with your allowed domains
3. Use PostgreSQL with SSL
4. Set up proper logging and monitoring
5. Use a process manager like systemd or Docker
6. Configure reverse proxy (nginx) with HTTPS
