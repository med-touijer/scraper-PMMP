# Marches Publics API - Production Deployment Guide

## Prerequisites

- Docker and Docker Compose installed
- SSL certificates for HTTPS
- Domain name configured
- At least 4GB RAM and 20GB storage

## Quick Start

1. **Clone the repository**
```bash
git clone <your-repo>
cd marches-publics-api
```

2. **Setup environment variables**
```bash
cp .env.example .env
# Edit .env with your production values
```

3. **Create SSL certificates directory**
```bash
mkdir -p docker/ssl
# Copy your SSL certificates to docker/ssl/cert.pem and docker/ssl/key.pem
```

4. **Start the services**
```bash
docker-compose up -d
```

## Environment Configuration

### Required Environment Variables

```bash
# Database
MONGODB_USERNAME=admin
MONGODB_PASSWORD=your-secure-password
MONGODB_DB_NAME=marches_publics

# Redis
REDIS_PASSWORD=your-redis-password

# Security
SECRET_KEY=your-super-secret-key-min-32-chars
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_PASSWORD=secure-admin-password

# CORS
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# Optional: Monitoring
GRAFANA_PASSWORD=grafana-admin-password
```

### SSL Configuration

Place your SSL certificates in `docker/ssl/`:
- `cert.pem` - SSL certificate
- `key.pem` - Private key

For development, generate self-signed certificates:
```bash
openssl req -x509 -newkey rsa:4096 -keyout docker/ssl/key.pem -out docker/ssl/cert.pem -days 365 -nodes
```

## Service Architecture

### Core Services

1. **MongoDB** (port 27017)
   - Primary database
   - Automatic backups recommended

2. **Redis** (port 6379)
   - Caching and rate limiting
   - Celery message broker

3. **FastAPI Application** (port 8000)
   - Main API server
   - 4 worker processes by default

4. **Celery Worker**
   - Background task processing
   - Handles scraping jobs

5. **Celery Beat**
   - Scheduled task management
   - Daily scraping automation

6. **Nginx** (ports 80, 443)
   - Reverse proxy
   - SSL termination
   - Rate limiting

### Optional Services

7. **Prometheus** (port 9090)
   - Metrics collection
   - Enable with: `docker-compose --profile monitoring up -d`

8. **Grafana** (port 3001)
   - Monitoring dashboards
   - Enable with: `docker-compose --profile monitoring up -d`

## API Endpoints

### Authentication
- `POST /api/v1/auth/login` - User login
- `POST /api/v1/auth/refresh` - Refresh token
- `POST /api/v1/auth/register` - Register user (Admin only)
- `GET /api/v1/auth/me` - Current user info

### Announcements
- `GET /api/v1/announcements/` - List announcements (paginated)
- `GET /api/v1/announcements/{id}` - Get announcement
- `POST /api/v1/announcements/` - Create announcement (Admin)
- `PUT /api/v1/announcements/{id}` - Update announcement (Admin)
- `DELETE /api/v1/announcements/{id}` - Delete announcement (Admin)
- `GET /api/v1/announcements/stats/overview` - Statistics
- `GET /api/v1/announcements/search/text` - Text search
- `GET /api/v1/announcements/expiring/soon` - Expiring announcements

### Scraper Management
- `GET /api/v1/scraper/status` - Scraper status
- `POST /api/v1/scraper/start` - Start scraping (Admin)
- `POST /api/v1/scraper/stop` - Stop scraping (Admin)
- `POST /api/v1/scraper/test` - Test scraping (Admin)
- `POST /api/v1/scraper/schedule` - Schedule scraping (Admin)

### System
- `GET /health` - Health check
- `GET /health/detailed` - Detailed health check
- `GET /api/v1/docs` - API documentation

## Security Features

### Authentication & Authorization
- JWT-based authentication
- Role-based access control (Admin, User, Viewer)
- Token refresh mechanism
- Secure password hashing (bcrypt)

### Rate Limiting
- API endpoints: 100 requests/minute
- Login endpoint: 5 requests/minute
- Configurable per endpoint

### Security Headers
- HSTS enabled
- XSS protection
- Content type validation
- CORS configuration
- CSP headers

### Data Protection
- Input validation with Pydantic
- SQL injection prevention
- HTTPS enforcement
- Secure cookie settings

## Monitoring & Logging

### Logging
- Structured logging with Loguru
- File rotation (10MB files, 30 days retention)
- Request/response logging
- Error tracking

### Health Checks
- Application health endpoint
- Database connectivity checks
- Automatic service restart on failure
- Container health monitoring

### Metrics (Optional)
- Prometheus metrics collection
- Grafana dashboards
- Custom business metrics
- Alert configuration

## Backup Strategy

### Database Backup
```bash
# Create backup
docker exec marches_publics_db mongodump --out /backup --db marches_publics

# Restore backup
docker exec marches_publics_db mongorestore /backup
```

### Automated Backups
Add to crontab:
```bash
0 2 * * * docker exec marches_publics_db mongodump --out /backup/$(date +\%Y\%m\%d) --db marches_publics
```

## Scaling

### Horizontal Scaling
```yaml
# In docker-compose.yml, scale API workers:
services:
  api:
    deploy:
      replicas: 3
  
  celery_worker:
    deploy:
      replicas: 2
```

### Performance Optimization
- Database indexing
- Redis caching
- CDN for static assets
- Connection pooling
- Resource limits

## Maintenance

### Update Application
```bash
# Pull latest changes
git pull origin main

# Rebuild and restart
docker-compose build --no-cache
docker-compose up -d
```

### Clean Up
```bash
# Remove old containers and images
docker system prune -a

# Clean up logs
docker-compose logs --since 24h > backup.log
docker-compose down && docker-compose up -d
```

### Database Maintenance
```bash
# Compact database
docker exec marches_publics_db mongo --eval "db.runCommand({compact: 'announcements'})"

# Reindex collections
docker exec marches_publics_db mongo --eval "db.announcements.reIndex()"
```

## Troubleshooting

### Common Issues

1. **MongoDB Connection Issues**
   - Check network connectivity
   - Verify credentials in environment
   - Check MongoDB logs: `docker logs marches_publics_db`

2. **High Memory Usage**
   - Monitor with `docker stats`
   - Adjust worker processes
   - Check for memory leaks

3. **Slow API Responses**
   - Check database indexes
   - Monitor query performance
   - Review rate limiting settings

4. **SSL Certificate Issues**
   - Verify certificate validity
   - Check file permissions
   - Test with SSL tools

### Log Analysis
```bash
# API logs
docker logs marches_publics_api -f

# Database logs
docker logs marches_publics_db

# Nginx access logs
docker exec marches_publics_nginx tail -f /var/log/nginx/access.log

# System resource usage
docker stats
```

## Development vs Production

### Development Setup
```bash
# Use development configuration
cp .env.example .env
# Set DEBUG=true, simpler passwords

# Run without SSL
docker-compose -f docker-compose.dev.yml up -d
```

### Production Checklist
- [ ] Strong passwords and secrets
- [ ] SSL certificates configured
- [ ] HTTPS enforced
- [ ] Rate limiting enabled
- [ ] Monitoring setup
- [ ] Backup strategy implemented
- [ ] Log aggregation configured
- [ ] Security headers enabled
- [ ] Database indexes created
- [ ] Performance testing completed

## Support

For issues and questions:
- Check logs first
- Review configuration
- Test with minimal setup
- Document error messages
- Check resource usage

## API Usage Examples

### Authentication
```bash
# Login
curl -X POST "https://yourdomain.com/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@yourdomain.com&password=your-password"

# Use token
curl -X GET "https://yourdomain.com/api/v1/announcements/" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Search Announcements
```bash
# Basic search
curl "https://yourdomain.com/api/v1/announcements/?search=infrastructure&limit=10"

# Filtered search
curl "https://yourdomain.com/api/v1/announcements/?procedure=AO&acheteur_public=Ministry"
```

