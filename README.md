# BloodLink — Hospital-Centred Blood Donation Coordination

**A platform for coordinating blood requests, donor discovery, and hospital-led blood donation workflows.**

BloodLink is a full-stack web application designed to connect individuals, hospitals, and blood centres through a structured, hospital-centred blood coordination system. It aims to improve the discovery of blood donation resources while preserving patient privacy and ensuring that official blood requests are handled by healthcare organizations.

## Live Demo

| Component | URL |
|---|---|
| Frontend | https://blood-link-eta-sandy.vercel.app |
| Backend API | https://bloodlink-api-yw2e.onrender.com |
| API Documentation | https://bloodlink-api-yw2e.onrender.com/docs |
| API Health Check | https://bloodlink-api-yw2e.onrender.com/api/v1/platform/health |

> **Note:** The frontend and backend are deployed separately. Render's free-tier backend may take time to respond after a period of inactivity.

## Table of Contents

- [Overview](#overview)
- [Problem Statement](#problem-statement)
- [Design Principles](#design-principles)
- [Core Features](#core-features)
- [System Architecture](#system-architecture)
- [Technology Stack](#technology-stack)
- [Repository Structure](#repository-structure)
- [Getting Started](#getting-started)
- [Environment Configuration](#environment-configuration)
- [Database Migrations](#database-migrations)
- [Running the Application](#running-the-application)
- [API Documentation](#api-documentation)
- [Deployment Architecture](#deployment-architecture)
- [Security and Privacy](#security-and-privacy)
- [Development Status](#development-status)
- [Contributing](#contributing)
- [License](#license)

## Overview

BloodLink is built around a central principle: **blood coordination should be organized through healthcare institutions rather than unverified direct requests between individuals.**

The platform provides a foundation for discovering hospitals and blood centres, coordinating official blood requests, managing donor participation, and communicating relevant updates.

The project combines a React frontend, a FastAPI backend, and a PostgreSQL database. Database schema changes are managed through Alembic migrations.

## Problem Statement

Blood donation coordination can be fragmented across phone calls, informal messaging groups, social media posts, and disconnected healthcare networks.

This can make it difficult to:

- Find relevant hospitals and blood centres.
- Route blood requirements to the healthcare institution responsible for the patient.
- Coordinate donor participation through structured workflows.
- Maintain clear responsibility for official blood requests.
- Protect patient and donor information during coordination.

BloodLink aims to provide a structured digital platform for these workflows, with hospitals acting as the authority for official blood requests.

## Design Principles

### 1. Hospital-centred request management

Individuals can discover hospitals and identify the institution where a patient is receiving treatment. The hospital is responsible for creating and submitting the official blood request.

Individuals cannot directly submit official blood requests or coordinate blood donations through individual-to-individual chat.

### 2. Privacy by design

The platform is intended to minimize unnecessary exposure of sensitive information. Precise donor locations should not be exposed to other users.

### 3. Role-oriented workflows

The application is designed around distinct user categories, including:

- **Individuals:** Discover healthcare organizations and access individual-facing features.
- **Hospitals:** Manage hospital-led blood request and coordination workflows.
- **Blood centres and blood banks:** Support blood availability and donation coordination.
- **Administrators:** Support platform administration and oversight.

The exact availability of each workflow depends on the current implementation.

### 4. Structured coordination

BloodLink aims to organize blood requests, donor participation, and notifications through defined application workflows rather than relying on unstructured communication.

## Core Features

The platform is designed to support the following capabilities:

- **Authentication:** User sign-in and account creation.
- **Hospital discovery:** Find healthcare organizations relevant to a blood requirement.
- **Hospital-led blood requests:** Route patient needs to the treating hospital for official submission.
- **Donor coordination:** Provide a foundation for donor discovery and donation workflows.
- **Organization workflows:** Support hospital and blood-centre participation.
- **Notifications:** Provide a foundation for relevant coordination updates.
- **Role-oriented access:** Separate individual-facing functionality from organization and administrative workflows.
- **API-driven architecture:** Keep frontend presentation separate from backend business logic and persistence.

These capabilities describe the product scope; not every workflow should be assumed complete or production-validated.

## System Architecture

BloodLink uses a frontend-backend architecture with a managed PostgreSQL database.

```text
                  ┌──────────────────────┐
                  │       Users          │
                  │ Individuals, Hospitals│
                  │ Blood Centres, Admins │
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │ React + Vite         │
                  │ Frontend             │
                  │ Deployed on Vercel   │
                  └──────────┬───────────┘
                             │ HTTP / JSON
                             ▼
                  ┌──────────────────────┐
                  │ FastAPI Backend      │
                  │ Authentication, API  │
                  │ Business Logic       │
                  │ Deployed on Render   │
                  └──────────┬───────────┘
                             │ SQLAlchemy
                             ▼
                  ┌──────────────────────┐
                  │ PostgreSQL           │
                  │ Managed by Neon      │
                  └──────────────────────┘
```

### Architectural responsibilities

| Component | Responsibility |
|---|---|
| React + Vite | User interface and client-side interactions |
| FastAPI | HTTP API, request validation, and application logic |
| SQLAlchemy | Database models and database access |
| Alembic | Versioned database schema migrations |
| PostgreSQL | Persistent application data |
| Neon | Managed PostgreSQL hosting |
| Vercel | Frontend build and deployment |
| Render | Backend application hosting |

## Technology Stack

| Layer | Technologies |
|---|---|
| Frontend | React 18, Vite, JavaScript/TypeScript as used by the frontend |
| Backend | Python, FastAPI, Uvicorn |
| Data validation | Pydantic |
| ORM | SQLAlchemy 2 |
| Database | PostgreSQL |
| Database migrations | Alembic |
| PostgreSQL driver | psycopg 3 |
| Frontend hosting | Vercel |
| Backend hosting | Render |
| Database hosting | Neon |
| Version control | Git and GitHub |

## Repository Structure

The repository is organized as a monorepo, containing the frontend, backend, shared packages, and database migration configuration.

```text
BloodLink/
├── apps/
│   ├── web/                  # React + Vite frontend
│   └── api/
│       └── bloodlink_api/    # FastAPI application
├── packages/
│   ├── config/               # Shared configuration
│   ├── contracts/            # Shared API contracts
│   ├── validation/           # Shared validation utilities
│   └── ui/                   # Shared UI package
├── alembic/
│   └── versions/             # Database migration revisions
├── alembic.ini               # Alembic configuration
├── requirements.txt          # Base Python dependencies
├── requirements-postgres.txt # PostgreSQL runtime dependencies
├── pyproject.toml            # Python project configuration
├── package.json              # Root JavaScript workspace configuration
├── .gitignore
└── README.md
```

Additional files may exist in the repository; this tree highlights the principal application components.

## Getting Started

### Prerequisites

Install the following tools before developing locally:

- Git
- Node.js and npm
- Python 3.12 or later
- PostgreSQL, or access to a PostgreSQL instance such as Neon

The deployed application uses Neon PostgreSQL. For local development, configure a separate development database.

### 1. Clone the repository

```bash
git clone https://github.com/thirukkumaran-student/BloodLink.git
cd BloodLink
```

### 2. Set up the Python environment

On Windows PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-postgres.txt
```

On Linux or macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-postgres.txt
```

### 3. Install frontend dependencies

From the repository root:

```bash
npm install
```

The repository uses workspace packages. Install dependencies from the root so the package manager can resolve the configured workspace structure.

If your local package-manager configuration specifies a different package manager, follow the repository's workspace configuration.

### 4. Configure environment variables

Create a local `.env` file at the repository root. Configure the variables described in the next section.

Do not commit `.env` files or production credentials.

### 5. Apply database migrations

After configuring the database URL, activate the virtual environment and run:

```bash
python -m alembic upgrade head
```

This creates or updates the database schema to match the migration history.

### 6. Start the application

Start the backend and frontend in separate terminals using the commands in [Running the Application](#running-the-application).

## Environment Configuration

The backend reads its configuration from environment variables. The following variables are relevant to the current deployment.

| Variable | Purpose |
|---|---|
| `BLOODLINK_ENV` | Application environment, such as `dev` or `production` |
| `BLOODLINK_SECRET_KEY` | Application secret; use a secure, randomly generated value |
| `BLOODLINK_DATABASE_URL` | SQLAlchemy database connection URL |
| `BLOODLINK_SEED_ON_STARTUP` | Controls whether startup seeding is enabled |
| `BLOODLINK_CORS_ORIGINS` | JSON array of allowed frontend origins |

Example development configuration:

```dotenv
BLOODLINK_ENV=dev
BLOODLINK_SECRET_KEY=replace-with-a-local-development-secret
BLOODLINK_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
BLOODLINK_SEED_ON_STARTUP=true
BLOODLINK_CORS_ORIGINS=["http://localhost:5173"]
```

Replace the database placeholders with your actual database credentials. The example is a template, not a ready-to-use connection string.

For local PostgreSQL, use the connection details of your local database. For Neon, use the connection URL supplied by Neon and ensure it uses the `postgresql+psycopg://` SQLAlchemy driver prefix.

### Production configuration

Configure production values in the hosting provider's environment-variable settings rather than committing them to the repository.

Production should use:

- `BLOODLINK_ENV=production`
- A randomly generated secret of at least 32 characters.
- The Neon PostgreSQL connection URL.
- `BLOODLINK_SEED_ON_STARTUP=false`
- `BLOODLINK_CORS_ORIGINS=["https://your-actual-frontend-domain"]`

Replace the example frontend domain with the actual production origin. The CORS value must be a valid JSON array.

**Never publish database URLs containing credentials, secret keys, or other private environment values.**

## Database Migrations

BloodLink uses Alembic to track database schema changes.

The current initial migration is:

```text
c8241b44b4d7 — initial schema
```

Useful commands:

**Apply all pending migrations**

```bash
python -m alembic upgrade head
```

**Check the current database revision**

```bash
python -m alembic current
```

**List available migration heads**

```bash
python -m alembic heads
```

**View migration history**

```bash
python -m alembic history
```

Database migrations should be applied before deploying backend changes that depend on the new schema.

Avoid manually modifying the production schema or running migrations against an unintended database.

## Running the Application

### Backend

Activate the Python virtual environment, configure the environment variables, and run the API from the repository root:

```bash
PYTHONPATH=apps/api:packages/config:packages/contracts:packages/validation uvicorn bloodlink_api.main:app --host 127.0.0.1 --port 8000
```

On Windows PowerShell, set the import path with:

```powershell
$env:PYTHONPATH = "apps/api;packages/config;packages/contracts;packages/validation"
```

Then run:

```powershell
uvicorn bloodlink_api.main:app --host 127.0.0.1 --port 8000
```

The backend will be available at:

```text
http://localhost:8000
```

### Frontend

In a separate terminal, from the repository root:

```bash
npm run dev --workspace=apps/web
```

The Vite development server is expected at:

```text
http://localhost:5173
```

If the workspace script differs in your current checkout, inspect `package.json` in the root and `apps/web` and use the configured development script.

## API Documentation

FastAPI provides interactive API documentation when the backend is running.

**Local documentation**

http://localhost:8000/docs

**Production documentation**

https://bloodlink-api-yw2e.onrender.com/docs

The API uses the `/api/v1` prefix for versioned endpoints. The platform health endpoint is:

```text
/api/v1/platform/health
```

Production health check:

https://bloodlink-api-yw2e.onrender.com/api/v1/platform/health

Use the interactive documentation to inspect available routes, request schemas, and response models.

## Deployment Architecture

BloodLink is deployed using three managed services.

| Service | Provider | Responsibility |
|---|---|---|
| Frontend | Vercel | Hosts the React + Vite application |
| Backend | Render | Runs the FastAPI application |
| Database | Neon | Provides managed PostgreSQL |

### Frontend deployment

The frontend is deployed from the GitHub repository using Vercel.

Production URL:

https://blood-link-eta-sandy.vercel.app

The frontend must be configured to call the deployed backend rather than a localhost development URL.

### Backend deployment

The backend is deployed as a Python web service on Render.

Production URL:

https://bloodlink-api-yw2e.onrender.com

Its startup command is:

```bash
PYTHONPATH=apps/api:packages/config:packages/contracts:packages/validation uvicorn bloodlink_api.main:app --host 0.0.0.0 --port $PORT
```

The build command is:

```bash
pip install -r requirements-postgres.txt
```

### Database deployment

The application uses a PostgreSQL database hosted by Neon in the AWS Asia Pacific (Singapore) region.

Database migrations are run using Alembic. The database connection URL is configured as a private environment variable in the backend hosting environment.

### CORS configuration

The backend must allow the deployed frontend origin.

Example:

```json
["https://blood-link-eta-sandy.vercel.app"]
```

Keep this value synchronized with the actual frontend domain. If a custom domain is added, configure that origin as well.

### Free-tier considerations

The project currently uses free-tier hosting. Availability, resource limits, and cold-start latency depend on the providers' free-tier policies. The application should not be assumed to have production-grade availability guarantees.

## Security and Privacy

BloodLink handles workflows that can involve sensitive patient and donor information. Security and privacy must remain central to development.

Key design requirements include:

- **Hospital-authorized requests:** Individuals cannot directly submit official blood requests.
- **No individual-to-individual chat:** Blood coordination should follow the platform's organization-centred workflows.
- **Donor location privacy:** Do not expose precise donor locations to other users.
- **Secret management:** Store production credentials in hosting-provider environment variables.
- **Production configuration:** Use secure secrets and disable automatic development seeding.
- **Database change control:** Apply schema changes through reviewed Alembic migrations.
- **Access control:** Verify authorization and role restrictions on the backend, not only in the frontend.

These are design requirements; each security control must be independently tested before the application is used for real patient or donor coordination.

## Development Status

BloodLink is an evolving full-stack project.

The initial deployment of the React frontend, FastAPI backend, and Neon PostgreSQL database is complete. The initial database migration has been applied.

The existence of a live deployment does not imply that all role-specific workflows, authorization rules, or end-to-end scenarios are complete. Authentication, hospital request handling, donor workflows, blood-centre workflows, and production security should be tested as their implementation evolves.

## Contributing

Contributions should preserve BloodLink's architecture and domain rules.

A typical contribution workflow is:

1. Create a feature branch.
2. Implement the change within the appropriate application or shared package.
3. Add or update tests.
4. Create an Alembic migration if the database schema changes.
5. Run relevant checks locally.
6. Submit a pull request for review.

For database or API changes, coordinate shared contracts and migration history before merging to avoid incompatible changes across the frontend and backend.

## License

All rights reserved.

This repository does not grant permission to copy, redistribute, modify, or commercially use the software unless the copyright holder provides authorization.

See the repository's `LICENSE` file for the applicable terms.
