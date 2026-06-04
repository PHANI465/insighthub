# main.py
# FastAPI application entry point for InsightHub backend.
# Creates the FastAPI app instance, registers all API routers, configures
# CORS, adds middleware (auth, logging, rate-limiting), and wires up the
# database connection pool on startup / teardown.
