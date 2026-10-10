# CLAUDE.md — MBA SIAF Exam Platform

## Mission
Build, test, version and deploy a production-ready, Spanish-language MBA assessment platform in Azure. Follow `docs/01_PRD.md`, `docs/02_ARCHITECTURE.md`, `docs/03_DATA_MODEL.md`, `docs/04_ASSESSMENT_ENGINE.md`, `docs/05_SECURITY.md`, `docs/06_DEPLOYMENT.md`, `docs/07_TEST_PLAN.md`, `docs/08_ACADEMIC_BANK.md` and `docs/09_ACCEPTANCE.md`.

## Non-negotiable
- NEVER invent 480 questions or claim the bank is complete without a validated 480-record export sourced to supplied course PDFs.
- The question bank is a separate deliverable, with review status, citations to PDF/page and quality gates. Read source materials; do not rely on generic knowledge to fill academic gaps.
- The Ivey Knight Capital case is copyrighted: use as conceptual inspiration only, no redistribution of case content, figures or text in the student product.
- No answer keys in client bundles or API student responses. Grade server-side; keep audit trails.
- No insecure client-only timers, identity, grade or localStorage persistence. Implement authoritative server deadlines and transactional writes.
- Do not commit secrets, passwords, tokens, Azure publish profiles, or student PII. `.env.example` only.
- Do not create or change Azure resources, push Git, or incur spend until operator explicitly approves the plan, subscription, resource group, region, pricing and repository.
- Always execute unit/integration/E2E tests and summarize actual results. Never report deployment success without verifying endpoint and health check.
- Make commits at meaningful milestones. No destructive migrations without backup and explicit approval.

## Architecture decisions (override older text in docs)
- ADR-001: Azure Database for PostgreSQL Flexible Server + SQLAlchemy 2 + Alembic (no Azure SQL).
- ADR-002: API in Azure Functions Python 3.12 (v2 model, Flex Consumption).
- ADR-003: multi-university, multi-subject platform with PostgreSQL Row-Level Security; SIAF is the first subject. No subject-specific values hard-coded.
- ADR-004: student access = university code + matrícula + convocatoria code against a roster (identity not verified; documented risk).
- The operator runs every `git push` and `az` command manually; Claude provides commands one at a time and verifies output.

## Workflow
1. Inspect repository and PDFs; inventory available Azure tooling, credentials and repo access; report gaps.
2. Produce implementation plan and cost estimate. Ask for approvals on Azure actions.
3. Scaffold React/Vite/TypeScript, Azure Functions (Python 3.12), PostgreSQL migrations (Alembic) and tests.
4. Implement secure admin import and bank QA, student exam engine and admin reporting.
5. Generate academic question bank in reviewable batches, verify 480 unique approved items; import only after teacher approval.
6. Run tests and security checks; prepare IaC and CI/CD; deploy after explicit approval.
7. Record actual URLs, build SHA, migration version, tests and rollback procedure.

## Delivery priorities
Reliable, fair and auditable assessment > UI decoration. The exam may not be activated until bank, identity, timing, scoring and persistence acceptance gates pass.
