# Contributing to Clipo

Thanks for your interest in contributing! 🎬 Clipo is a local-first AI clip studio — long-form video in, social-ready short clips out.

This guide covers how to set up the project locally, what conventions to follow, and how to get your changes merged.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Coding Conventions](#coding-conventions)
- [Running Checks](#running-checks)
- [Git Workflow](#git-workflow)
- [Commit Message Style](#commit-message-style)
- [Reporting Issues](#reporting-issues)
- [Auto-updated Docs](#auto-updated-docs)

## Code of Conduct

Be respectful and constructive. This is a small, friendly project — treat other contributors the way you'd like to be treated. Harassment, trolling, and spam are not welcome.

## How to Contribute

1. **Ask first** — open an issue or discussion describing what you want to build or fix. The maintainers may already be working on it or have a different design in mind.
2. **Fork** the repo and create a branch for your work.
3. **Keep changes focused** — one logical change per PR makes review faster and safer.
4. **Open a Pull Request** against `main` and describe what you changed and why.

Not sure where to start? Good first contributions:

- Fix a bug from the [Issues](https://github.com/SACHINN122/Clipo/issues) list
- Improve error messages shown to users
- Add tests or improve documentation
- Polish responsive/mobile behavior in the frontend

## Development Setup

### Prerequisites

- **FFmpeg** on your `PATH` (the backend exits at startup if it's missing)
- Python 3.10+
- Node.js 18+

### 1. Clone and install

```bash
git clone https://github.com/SACHINN122/clipo.git
cd clipo
```

### 2. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # macOS / Linux
# .\venv\Scripts\Activate.ps1  # Windows PowerShell

pip install -r requirements.txt
```

Create `backend/.env`:

```env
GEMINI_API_KEY=your_key_here

# Optional: use NVIDIA NIM instead of Gemini
# AI_PROVIDER=nvidia
# NVIDIA_API_KEY=your_nvidia_key

# Optional: Google OAuth login
# GOOGLE_CLIENT_ID=your_client_id
# GOOGLE_CLIENT_SECRET=your_client_secret
# FRONTEND_URL=http://localhost:5173
# BACKEND_URL=http://localhost:8001
```

Run the backend:

```bash
cd backend
python main.py      # → http://localhost:8001
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev         # → http://localhost:5173
```

Open **http://localhost:5173** in your browser.

## Project Structure

```
backend/
  main.py              # FastAPI entry point + startup checks
  config.py            # Env-driven settings
  routes/              # API and auth routes
  services/            # Pipeline, AI, transcription, FFmpeg
  models/              # Data models
  requirements.txt
frontend/
  src/
    components/        # UI components (screens, shared pieces)
    lib/               # Client helpers (API, notifications, sound)
    App.jsx            # Root app + app-level watchers
  package.json
images/
  star-history.svg     # Auto-generated (see below)
.github/
  scripts/             # Auto-update scripts for docs
  workflows/           # CI / automation
```

## Coding Conventions

- **Frontend:** React + Vite + Tailwind. Prefer existing components and patterns over new abstractions.
- **Backend:** FastAPI + Python. Match the surrounding style; keep API handlers thin and logic in `services/`.
- **No secrets in code.** All keys and tokens come from `backend/.env` (see `config.py`). Never commit `.env` or credentials.
- **Don't commit generated files** unless they're intentionally versioned (e.g., `images/star-history.svg`).
- Keep pull requests small and self-contained.

## Running Checks

Before opening a PR, make sure the app builds:

```bash
# Frontend
cd frontend
npm run build        # type-safe production build
npm run lint         # oxlint

# Backend
cd backend
python -c "import main"   # smoke-check imports
```

Then run the app end-to-end once: upload a short clip (or paste a YouTube URL), process it, and confirm a clip is produced with captions.

## Git Workflow

1. Branch off `main` with a descriptive name:

   ```bash
   git checkout -b feat/your-feature
   ```

2. Commit your work with clear messages (see below).
3. Push your branch and open a PR against `main`.
4. Keep your branch up to date:

   ```bash
   git fetch origin
   git rebase origin/main
   ```

5. Respond to review feedback. Once CI passes and a maintainer approves, your PR is merged.

## Commit Message Style

We use conventional, scope-tagged commit messages:

```text
feat(ui): add dark mode toggle
fix(clips): scale ffmpeg timeout for long videos
docs(readme): document completion alerts
```

- Prefix: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `style`
- Optional scope in parentheses, e.g. `auth`, `clips`, `ui`, `render`, `youtube`
- Present tense, imperative mood, lowercase after the prefix
- Keep the subject under ~72 characters; add a body only when extra context helps

## Reporting Issues

Include:

- What you expected vs. what happened
- Steps to reproduce
- Your environment (OS, browser, backend/frontend versions)
- Relevant logs or error messages
- For YouTube issues: the source URL and whether it's an upload or a link

## Auto-updated Docs

The README's **Star History chart** and **Contributors** section are generated by GitHub Actions:

- `.github/workflows/update-contributors.yml` runs nightly and on every push to `main`
- It regenerates `images/star-history.svg` and the contributors block from live GitHub data
- **Don't hand-edit those sections or the SVG** — edit `.github/scripts/update_contributors.py` or `.github/scripts/update_star_history.py` instead, then let the workflow regenerate them
