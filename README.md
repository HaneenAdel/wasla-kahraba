# Wasla Kahraba

Wasla Kahraba is a web application that helps people find charging points for phones and small devices. Users can search in Arabic by area, service, and availability, and view details such as opening hours, capacity, waiting count, and the latest update. Charging-point owners can manage their own locations through a dedicated interface.

## Features

- Direct and natural-language search for charging points.
- Semantic search using embeddings to find points related to a query.
- Charging-point status display: available, full, or closed.
- An owner interface for updating point details or deleting a point after confirmation.
- Ownership checks before allowing updates or deletions.
- Local fallback responses when no API key is configured.

## Technology

- Python and Flask for the application and API endpoints.
- SQLite for charging points, owners, and agent-role configuration.
- HTML, CSS, and JavaScript for the user interfaces.
- The OpenAI Python SDK, optionally, for understanding requests and generating responses.

## Getting Started

Python 3.10 or later is required.

Install the dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run the application:

```powershell
python app.py
```

Then open [http://localhost:8080](http://localhost:8080). Flask runs in development mode; do not use the development server for public deployments.

## Deploy to Render

The repository includes a Render Blueprint in `render.yaml`. Push it to GitHub, then create a Blueprint in Render from this repository. Render installs `requirements.txt`, generates `SECRET_KEY`, and provides the public service URL after deployment.

The free plan uses an ephemeral filesystem. SQLite data changes may be lost when the service restarts or redeploys; use persistent storage or an external database for production.

## Model Configuration

Search and responses can use local fallback behavior without an API key. To use the OpenAI SDK, set these environment variables before starting the application:

```powershell
$env:OPENAI_API_KEY = "your-api-key"
$env:OPENAI_MODEL = "gpt-5-mini"
python app.py
```

`OPENAI_MODEL` is optional and defaults to `gpt-5-mini`. The application reads `OPENAI_API_KEY` from the system environment; it does not automatically load `env.example`.

## Data

When the application starts, it creates the SQLite tables and loads initial data from CSV files in `flask_app/database/initial_data/`. The database is stored at `flask_app/database/wasla_kahraba.db`. Seeding uses `INSERT OR IGNORE`, so existing records are not deleted when the application restarts.

## User Interfaces

- `/` — Public search interface.
- `/owner` — Owner sign-in and charging-point management.

Use one of these demo owner keys to try the owner interface:

- `demo-owner-key-001`
- `demo-owner-key-002`

## API

- `GET /api/chargepoints` — Returns charging points and supports the `q` search parameter.
- `POST /api/smart-search` — Performs a natural-language search. Example body: `{"message": "Find a phone charging point in the central area"}`.
- `GET /api/chargepoints/semantic-search?q=...` — Performs semantic search.
- `POST /api/owner/login` and `POST /api/owner/logout` — Sign an owner in or out.
- `GET /api/owners/<owner_id>/chargepoints` — Returns charging points for the signed-in owner.
- `PUT /api/chargepoints/<chargepoint_id>` — Updates a point owned by the signed-in user.
- `DELETE /api/chargepoints/<chargepoint_id>` — Deletes a point owned by the signed-in user.
- `POST /api/owner/assistant` — Interacts with the owner assistant.

Owner operations require an authenticated session. The server verifies ownership before applying updates or deletions.

## Project Structure

```text
app.py                         Flask entry point
flask_app/
  routes.py                    Application pages and API endpoints
  templates/                   Search and owner pages
  static/                      CSS, JavaScript, and image assets
  utils/
    agents.py                  Search and write agents, plus request orchestration
    database.py                SQLite data access
    embeddings.py              Embedding generation and search
    llm.py                     Request understanding and response generation
  database/
    create_tables/             Table schemas
    initial_data/              Initial CSV data
```