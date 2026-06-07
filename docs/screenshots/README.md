# InsightHub — Screenshots

Add the following PNG files to this directory to populate the Screenshots section in the main README.

## Required Files

| Filename | Page to Capture | URL |
|----------|----------------|-----|
| `01-login.png` | Login page — shows the demo banner and credentials hint | `http://localhost:3000/login` |
| `02-dashboard.png` | Executive Dashboard — all 5 KPI cards + revenue chart + campaign ROI bar visible | `http://localhost:3000/dashboard` |
| `03-customers.png` | Customer Analytics — segment table + revenue bar + pie chart | `http://localhost:3000/customers` |
| `04-support.png` | Support Operations — 4 KPI cards + ticket volume + resolution chart | `http://localhost:3000/support` |
| `05-ai-insights.png` | AI Insights — at least one expanded insight card with key_findings visible | `http://localhost:3000/insights` |

## Capture Instructions

1. Start the backend: `cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
2. Start the frontend: `cd frontend && npm run dev`
3. Log in as `admin` (can see all pages)
4. Navigate to each page and take a full-page screenshot
5. Crop to browser window only (no OS chrome/taskbar)
6. Save at 1440×900 or 1280×800 resolution — consistent across all five
7. Use PNG format (not JPEG — avoids text compression artifacts)

## Recommended Tools

- **Windows**: Snipping Tool (Win + Shift + S) → full window → save as PNG
- **macOS**: `⌘ + Shift + 4`, then Space to capture window
- **Browser**: DevTools → `⋮ → Run command → "Capture full size screenshot"`

## Notes

- Screenshots are **not committed to git** (`.gitignore` excludes `docs/screenshots/*.png`)
- They are linked from the README via relative paths so they render on GitHub
- If the backend is offline when a visitor views the README, the screenshots still show the UI
- Recommended: add screenshots before deploying so the GitHub README looks complete
