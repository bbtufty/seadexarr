# SeaDexArr

A modern, production-ready CLI tool for synchronizing your AniList anime and manga lists with Sonarr and Radarr media management systems.

## ✨ Features

- **🔄 Automated Sync**: Keep your Sonarr/Radarr libraries in sync with your AniList
- **🎯 Smart Configuration**: Platform-aware setup with intelligent defaults  
- **🚀 Modern CLI**: Beautiful Rich-formatted output with progress indicators
- **⚡ Async Performance**: Fast, non-blocking operations for better responsiveness
- **🐳 Docker Ready**: Production-grade containerization with multi-stage builds
- **🔧 Comprehensive**: Batch operations, search, status checking, and validation
- **🛡️ Robust**: Structured logging, proper error handling, and retry logic
- **🔄 Legacy Support**: Backward compatibility for existing workflows

## 🚀 Quick Start

### 1. Installation

```bash
# Install from source
git clone https://github.com/seadx/seadexarr.git
cd seadexarr
pip install -e .
```

### 2. Initialize Configuration

The fastest way to get started is using the `init` command, which creates a platform-specific configuration:

```bash
# Create .env file with sensible defaults for your platform
seadexarr init

# Or specify a custom location
seadexarr init --output=config/production.env
```

This will create a comprehensive `.env` file with:
- Platform-specific service URLs (Windows/Linux/Docker)
- All required and optional configuration options  
- Helpful comments and usage examples
- Environment detection (Docker, Windows, Linux/macOS)

### 3. Configure Your Services

Edit the generated `.env` file with your actual API keys and service URLs:

```bash
# Required: AniList access token
SEADEXARR_ANILIST_ACCESS_TOKEN=your_anilist_token

# Required: SeaDx API access  
SEADEXARR_SEADX_API_KEY=your_seadx_api_key

# Required: Sonarr configuration
SEADEXARR_SONARR_URL=http://localhost:8989
SEADEXARR_SONARR_API_KEY=your_sonarr_api_key

# Required: Radarr configuration
SEADEXARR_RADARR_URL=http://localhost:7878
SEADEXARR_RADARR_API_KEY=your_radarr_api_key
```

### 4. Validate Configuration

```bash
# Check your configuration
seadexarr config-validate

# Test service connectivity  
seadexarr status
```

### 5. Start Syncing

```bash
# Sync a single user to Sonarr
seadexarr sync sonarr your_anilist_username

# Preview changes first (dry run)
seadexarr sync sonarr your_anilist_username --dry-run

# Sync to Radarr for movies
seadexarr sync radarr your_anilist_username

# Batch sync multiple users
seadexarr sync-batch user1 user2 user3 --target=sonarr
```

## 📋 Available Commands

| Command | Description |
|---------|-------------|
| `init` | Initialize platform-specific configuration file |
| `sync sonarr` | Sync AniList anime to Sonarr series |
| `sync radarr` | Sync AniList movies to Radarr |
| `sync-batch` | Batch sync multiple users to target service |
| `search-releases` | Search and preview SeaDx releases |
| `status` | Check connectivity to all configured services |
| `config-validate` | Validate current configuration settings |
| `config-info` | Display current configuration (alias for validate) |

## 📥 Installation

### Python Package (Recommended)

```bash
pip install seadexarr
```

### Development Installation

```bash
git clone https://github.com/bbtufty/seadexarr.git
cd seadexarr
pip install -e .
```

### Docker

```yaml
services:
  seadexarr:
    image: ghcr.io/bbtufty/seadexarr:latest
    container_name: seadexarr
    environment: 
      - SEADEXARR_ANILIST_ACCESS_TOKEN=your_token
      - SEADEXARR_SEADX_API_KEY=your_key
      - SEADEXARR_SONARR_URL=http://sonarr:8989
      - SEADEXARR_SONARR_API_KEY=your_sonarr_key
      - SEADEXARR_RADARR_URL=http://radarr:7878
      - SEADEXARR_RADARR_API_KEY=your_radarr_key
      - SEADEXARR_LOG_LEVEL=INFO
    volumes:
      - ./config:/config
    restart: unless-stopped
```

## 📖 CLI Reference

### Main Commands

```bash
seadexarr --help                    # Show all commands
seadexarr --verbose                 # Enable verbose output
seadexarr --quiet                   # Show only errors
seadexarr --dry-run                 # Preview mode (no changes)
```

### Sync Commands

```bash
# Individual sync operations
seadexarr sync sonarr USERNAME [OPTIONS]
seadexarr sync radarr USERNAME [OPTIONS]

# Batch operations  
seadexarr sync-batch USER1 USER2 USER3 [OPTIONS]
  --target=sonarr|radarr           # Target service
  --concurrent=N                   # Max concurrent syncs (default: 3)
  --dry-run                        # Preview changes
```

### Utility Commands

```bash
# Search releases
seadexarr search-releases "TITLE" [OPTIONS]
  --quality=FILTER                 # Quality filter (can use multiple)
  --limit=N                        # Max results (default: 10)
  --dry-run/--download            # Preview or download mode

# System status
seadexarr status                   # Check all services
seadexarr config-validate         # Validate configuration
seadexarr config-info             # Show current config
```

### Legacy Compatibility

```bash
# Legacy format still works
seadexarr --sonarr myusername --dry-run
seadexarr --radarr myusername --dry-run
```

## 🛠️ How SeaDexArr Works

SeaDexArr performs intelligent filtering to find the best releases:

1. **Service Integration**: Connects to AniList for user lists, Sonarr/Radarr for media management
2. **Release Matching**: Maps series via TVDB/IMDb IDs using Kometa and AniDB mappings  
3. **Quality Filtering**: Applies tracker preferences, quality filters, and SeaDx "best" tags
4. **Smart Selection**: Chooses optimal releases based on your preferences
5. **Automated Import**: Adds releases to your torrent client and Arr apps

### Release Selection Criteria

SeaDexArr applies filters in this order:

1. **Tracker Filtering**: Include/exclude specific trackers
2. **Privacy Filtering**: Public-only or include private trackers  
3. **Quality Tags**: Prefer "best" tagged releases when available
4. **Audio Preferences**: Dual audio vs Japanese-only selection
5. **Final Selection**: Choose best match or prompt for selection

## 🔧 Advanced Configuration

### Logging Configuration

```bash
# Console output (development)
SEADEXARR_LOG_FORMAT=console
SEADEXARR_LOG_LEVEL=DEBUG

# JSON output (production)  
SEADEXARR_LOG_FORMAT=json
SEADEXARR_LOG_LEVEL=INFO
```

### Performance Tuning

```bash
# Adjust HTTP settings
SEADEXARR_HTTP_TIMEOUT=60          # Longer timeout for slow networks
SEADEXARR_HTTP_RETRIES=5           # More retries for reliability

# Batch processing limits
seadexarr sync-batch users --concurrent=1  # Slower, more reliable
seadexarr sync-batch users --concurrent=5  # Faster, more aggressive
```

## 🐳 Docker Usage

### Docker Compose

```yaml
version: "3.8"
services:
  seadexarr:
    image: ghcr.io/bbtufty/seadexarr:latest
    container_name: seadexarr
    environment:
      # Core configuration
      - SEADEXARR_ANILIST_ACCESS_TOKEN=${ANILIST_TOKEN}
      - SEADEXARR_SEADX_API_KEY=${SEADX_API_KEY}
      
      # Sonarr integration
      - SEADEXARR_SONARR_URL=http://sonarr:8989
      - SEADEXARR_SONARR_API_KEY=${SONARR_API_KEY}
      
      # Radarr integration  
      - SEADEXARR_RADARR_URL=http://radarr:7878
      - SEADEXARR_RADARR_API_KEY=${RADARR_API_KEY}
      
      # Application settings
      - SEADEXARR_LOG_LEVEL=INFO
      - SEADEXARR_LOG_FORMAT=json
      - SEADEXARR_DRY_RUN=false
      
    volumes:
      - ./config:/config
      - ./logs:/app/logs
    restart: unless-stopped
    depends_on:
      - sonarr
      - radarr
```

### Docker Commands

```bash
# One-time sync
docker run --rm --env-file .env ghcr.io/bbtufty/seadexarr:latest sync sonarr myusername

# Check status
docker run --rm --env-file .env ghcr.io/bbtufty/seadexarr:latest status

# Interactive container
docker run -it --env-file .env ghcr.io/bbtufty/seadexarr:latest --help
```

## 🤔 Troubleshooting

### Common Issues

```bash
# Check configuration
seadexarr config-validate

# Test connectivity  
seadexarr status

# Enable debug logging
seadexarr --verbose sync sonarr myusername

# Validate specific config file
seadexarr config-validate /path/to/config.env
```

### Error Resolution

| Error | Solution |
|-------|----------|
| `AniList access token not configured` | Set `SEADEXARR_ANILIST_ACCESS_TOKEN` |
| `SeaDx API key not configured` | Set `SEADEXARR_SEADX_API_KEY` |  
| `Sonarr URL or API key not configured` | Set `SEADEXARR_SONARR_URL` and `SEADEXARR_SONARR_API_KEY` |
| `Service unreachable` | Check URLs and network connectivity |
| `Permission denied` | Verify API keys and user permissions |

## 📜 Legacy Usage (Deprecated)

The old class-based API is still available for backward compatibility:

```python
from seadexarr import SeaDexSonarr, SeaDexRadarr

sds = SeaDexSonarr()
sds.run()

sdr = SeaDexRadarr()  
sdr.run()
```

**⚠️ Note**: Legacy usage is deprecated. Please migrate to the new CLI for better functionality and support.

## 🗺️ Roadmap

- **Enhanced Mapping**: Improved episode mapping for OVAs and movies
- **More Torrent Clients**: Support for additional torrent clients beyond qBittorrent  
- **Additional Trackers**: Support for more public and private trackers
- **Web Interface**: Optional web UI for configuration and monitoring
- **Notification Systems**: Discord, Slack, and webhook notifications
- **Scheduling**: Built-in cron-like scheduling capabilities

## 🤝 Contributing

Contributions are welcome! Please check the [GitHub repository](https://github.com/bbtufty/seadexarr) for issues and development guidelines.

## 📄 License

SeaDexArr is licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE) for details.
