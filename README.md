# Roadmap Tracker

A personal roadmap, notes, projects, and calendar tracker built with Flask and SQLite.

Organize learning or career goals into roadmaps, break them into stages and topics, track projects and notes, and see all deadlines on a calendar.

## Features

- **Roadmaps** with title, description, and color, plus automatic progress percentage
- **Stages** inside each roadmap, ordered by position
- **Topics** with status (`not_started` / `in_progress` / `completed`), priority, and due date
- **Projects** with status, tech stack, repository URL, due date, and optional stage link
- **Notes** attachable to a roadmap, stage, or topic
- **Calendar view** aggregating topic and project deadlines via JSON API
- **CSV export/import** for backups and migrations (single file, all records)
- Server-rendered UI using Bootstrap and Bootstrap Icons (CDN)

## Tech Stack

- Python 3.12+
- Flask
- Flask-SQLAlchemy
- SQLite
- python-dotenv
- Ruff (linting/formatting)
- [uv](https://docs.astral.sh/uv/) for dependency management

## Getting Started

### Prerequisites

- Python 3.12+
- `uv`

### Setup

```bash
make install
cp .env.example .env   # adjust values as needed
make init-db           # optional; tables are also created on app startup
make run
```

The app runs at `http://127.0.0.1:5000`.

### Environment Variables

| Variable       | Default                     | Description                     |
| -------------- | --------------------------- | ------------------------------- |
| `SECRET_KEY`   | `dev-secret-key`            | Flask session secret            |
| `DATABASE_URL` | `sqlite:///roadmap.db`      | SQLAlchemy database connection  |
| `FLASK_APP`    | `src.main:app`              | Flask application entry point   |

The SQLite file is created in `instance/`.

## Usage

| Route                        | Description                        |
| ---------------------------- | ---------------------------------- |
| `/`                          | Roadmap dashboard                  |
| `/calendar`                  | Calendar of all deadlines          |
| `/api/calendar/events`       | JSON feed of topics/projects       |
| `/api/export/csv`            | Download a CSV backup              |
| `/roadmap/import/csv`        | Import a CSV backup (POST)         |

Creating, editing, deleting, and status-cycling items are handled through form `POST` routes defined in `src/main.py`.

### CSV Backup Format

The export is a single UTF-8 CSV file. Each row has a `type` (`roadmap`, `stage`,
`topic`, `project`, or `note`) and an `id` used by `parent_id`, `stage_id`, and
`topic_id` to preserve relationships:

| Column        | Used by                  | Description                              |
| ------------- | ------------------------ | ---------------------------------------- |
| `id`          | all                      | Unique key within the file               |
| `type`        | all                      | Record type                              |
| `parent_id`   | stage/topic/project/note | Roadmap id (or stage id for a topic)     |
| `stage_id`    | project/note             | Optional linked stage id                 |
| `topic_id`    | note                     | Optional linked topic id                 |
| `title`       | all                      | Required                                 |
| `description` | roadmap/stage/project    | Optional                                 |
| `color_hex`   | roadmap                  | `#RRGGBB` accent color                   |
| `status`      | topic/project            | `not_started`/`in_progress`/`completed` or `planned`/`in_progress`/`completed` |
| `priority`    | topic                    | `low`/`medium`/`high`                    |
| `due_date`    | topic/project            | `YYYY-MM-DD`                             |
| `position`    | stage/topic              | Integer sort order                       |
| `tech_stack`  | project                  | Optional                                 |
| `repo_url`    | project                  | Optional                                 |
| `content`     | note                     | Note body                                |

Export first to get a valid example. Import appends the records by default; check
**Replace all existing data** in the import dialog to restore a backup over the
current data.

## Project Structure

```
src/
  main.py              Flask app, models, routes, CSV import/export
  templates/
    base.html          Shared layout and navigation
    index.html         Roadmap dashboard
    calendar.html      Calendar view
instance/
  roadmap.db           SQLite database (gitignored)
Makefile               install / run / init-db / clean targets
pyproject.toml         Project metadata and dependencies
```

## Development

Run the development server with auto-reload:

```bash
make run
```

Lint the code:

```bash
uv run ruff check .
```

Reset the local database:

```bash
make clean
make init-db
```

## Data Model

- `Roadmap` has many `Stage`, `Project`, and `Note` records.
- `Stage` belongs to a `Roadmap` and has many `Topic` records.
- `Topic` belongs to a `Stage`.
- `Project` belongs to a `Roadmap` and optionally a `Stage`.
- `Note` belongs to a `Roadmap` and optionally a `Stage` or `Topic`.

Deleting a roadmap cascades to its stages, topics, projects, and notes.
