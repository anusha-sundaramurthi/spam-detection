# ClearVendor spam detection demo

Demo-only React + FastAPI system with a separate MongoDB database, deterministic rules, and a local Ollama model. Spam detection is the core concept. Vendors submit detailed services/packages and see status only; automatic scores and reasons are admin-only.

## Automatic workflow

1. Vendor signs in and submits the business, service, package, pricing, delivery, and offer details.
2. FastAPI automatically runs every mandatory rule service and the local AI spam review during submission. There is no manual **Run Assessment** action.
3. The vendor receives only an ID and `pending` status—never scores or reasons.
4. The admin sees the combined score, local-AI review, and side-by-side risk/trust point ledgers.
5. Admin approval remains a human action.

## Mandatory scoring services

- **Description, package, and offer spam screening (highest priority)**
- **Local AI semantic description review (Ollama + `llama3.2:3b`)**
- **Duplicate and copied-content screening**
- **Optional website threat-pattern screening when a URL is supplied**
- **Business trust-evidence screening**

The vendor's email comes from the authenticated login and is not a spam-scoring input. Website, social profiles, business registration, and special offers are optional; a supplied URL is still validated and screened.

Run `powershell -ExecutionPolicy Bypass -File scripts/check_local_services.ps1` to verify MongoDB, Ollama, and the model. Rules-only fallback prevents lost submissions, but full demo readiness requires all mandatory services.

## Required project structure

```text
clearvendor-mongodb-ai-demo/
├── backend/
│   ├── app/                  # API, auth, schemas, database, rules, AI, seeds
│   ├── tests/                # Auth, rules, combination, workflow tests
│   ├── .env.example          # Safe configuration template
│   └── requirements.txt      # Pinned Python dependencies
├── frontend/
│   ├── src/
│   │   ├── pages/            # Role-specific screens
│   │   ├── api.js            # API client
│   │   ├── components.jsx    # Reusable UI
│   │   └── styles.css/ai.css # Presentation
│   ├── package.json
│   └── vite.config.js
├── scripts/                  # Local dependency/readiness checks
└── README.md
```

### Source documentation convention

- Every comment-capable source file starts with a multiline `Purpose` header.
- Every named Python function, React component, and JavaScript helper has a concise single-line responsibility comment.
- `package.json` and `package-lock.json` remain comment-free because standard JSON does not permit comments.
- Route orchestration stays in `backend/app/main.py`; persistence, schemas, authentication, deterministic scoring, local AI, and seeding remain separate modules.

## Setup

Requirements: Python 3.11+, Node 20+, MongoDB, and Ollama.

```powershell
ollama pull llama3.2:3b

cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --env-file .env
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. API docs are at `http://localhost:8000/docs`.

Demo logins (change in `.env`): vendor `vendor@example.com` / `vendor-demo`; admin `admin@example.com` / `admin-demo`.

## Scoring model

Both risk and trust ledgers total 10 available points. Each factor stores its points, maximum, trigger/earned state, and human-readable evidence. If AI succeeds, combined scores use 60% rules and 40% local AI. If AI fails, the stored result explicitly says `rules_only`.

This is advisory demo output. Do not use it as the sole basis for vendor approval or production enforcement.
