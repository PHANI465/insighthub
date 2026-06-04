# test_api.py
# Pytest test suite for InsightHub FastAPI endpoints.
# Uses TestClient with a test database fixture to exercise:
#   - /api/health
#   - /api/metrics (with mock data)
#   - /api/search (mocked Azure AI Search responses)
#   - /api/insights (mocked OpenAI responses)
#   - Auth / token validation edge cases
