# config.py
# Centralised settings for the InsightHub backend using Pydantic BaseSettings.
# Reads all configuration from environment variables (loaded via .env in dev).
# Exposes typed settings for database, Azure services, auth, and CORS
# so nothing is hardcoded anywhere else in the codebase.
