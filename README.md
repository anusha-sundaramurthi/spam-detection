# onivah spam detection demo

Demo-only React + FastAPI system with a separate MongoDB database and AI-only local Ollama scoring. Llama is primary and Qwen is the automatic backup. Deterministic checks provide zero-weight evidence only. Vendors see status only; scores and reasons are admin-only.

Submission processing is save-first: React sends one multipart request, FastAPI validates and stores the raw record with `created_at`, `updated_at`, and `assessment_status: pending`, then a backend task reloads that MongoDB document, constructs the validated scoring input, and runs all assessment services. Address, package, price, and offer fields are included in spam detection. Optional images are verified on the backend by signature, dimensions, and SHA-256 duplicate detection; the configured text-only Llama/Qwen models do not claim visual scene understanding.

## Automatic workflow

1. Vendor signs in and submits the business, service, package, pricing, delivery, and offer details.
2. FastAPI automatically runs every mandatory rule service and the local AI spam review during submission. There is no manual **Run Assessment** action.
3. The vendor receives only an ID and `pending` status—never scores or reasons.
4. The admin sees the combined score, local-AI review, and side-by-side risk/trust point ledgers.
5. Admin approval remains a human action.

## Mandatory scoring services

- **Primary AI scoring (`llama3.2:3b`)**
- **Backup AI scoring (`qwen2.5:3b`)**
- **Zero-weight description, package, and offer evidence detection**
- **Zero-weight duplicate and campaign evidence detection**
- **Zero-weight optional URL evidence detection**

The vendor's email comes from the authenticated login and is not a spam-scoring input. Website, social profiles, business registration, and special offers are optional; a supplied URL is still validated and screened.

Run `powershell -ExecutionPolicy Bypass -File scripts/check_local_services.ps1` to verify MongoDB, Ollama, and the model. Rules-only fallback prevents lost submissions, but full demo readiness requires all mandatory services.

## Required project structure

```text
onivah-mongodb-ai-demo/
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
ollama pull qwen2.5:3b

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

Both risk and trust ledgers total 10 available points and are generated exclusively by the successful local AI model. Llama is attempted first; Qwen is attempted only when Llama fails or returns invalid structured output. If both fail, scores remain empty, the assessment is marked `ai_unavailable`, and admin approval is blocked. Deterministic content, URL, duplicate, and trust checks remain visible evidence with `scoring_weight: 0`.

This is advisory demo output. Do not use it as the sole basis for vendor approval or production enforcement.

## Explainable intelligence features

- Exact rule-matched phrases are highlighted in an admin-only spam evidence map.
- Counterfactuals estimate how much each triggered rule contributes to the combined risk score.
- Every assessment records whether primary Llama or fallback Qwen produced the score.
- Similar submissions are clustered into stable campaign identifiers using content, phone, and website evidence.
- Structured admin feedback records confirmed spam, false positives, accurate low-risk results, and unresolved reviews as an audit history. Feedback never silently retrains the model or changes scoring weights.

## Vendor registration and uploads

The vendor form requires address line 1, address line 2, city, state, country, and pincode. Aadhaar and GSTIN are optional and format-validated; Aadhaar is masked in the admin interface. Delivery timeline is not collected.

For the event-service marketplace, the universal required fields are business name, event-service category, phone, service title, detailed service description, and the structured address. Website, portfolio link, package name, price/range, package inclusions, special offer, social links, business registration, Aadhaar, GSTIN, service photos, and supporting file are optional. Missing portfolio or package data is neutral and does not reduce the AI score.

Vendors may optionally upload up to five JPEG/PNG/WebP service photos (5 MB each) and one PDF/DOC/DOCX supporting document (10 MB). Files are stored under the backend's ignored `uploads/` directory with randomized names; MongoDB stores metadata and ownership/link state. Upload references are ownership-verified before submission, and media retrieval is restricted to authenticated administrators.
