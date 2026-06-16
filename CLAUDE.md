# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

# GSTACK

For all web browsing, use the `/browse` skill from gstack. Never use `mcp__claude-in-chrome__*` tools.

Available gstack skills: /office-hours, /plan-ceo-review, /plan-eng-review, /plan-design-review, /design-consultation, /design-shotgun, /design-html, /review, /ship, /land-and-deploy, /canary, /benchmark, /browse, /connect-chrome, /qa, /qa-only, /design-review, /setup-browser-cookies, /setup-deploy, /setup-gbrain, /retro, /investigate, /document-release, /document-generate, /codex, /cso, /autoplan, /plan-devex-review, /devex-review, /careful, /freeze, /guard, /unfreeze, /gstack-upgrade, /learn

# PRODUCT VISION

Build a multi-tenant Restaurant Financial Intelligence Platform that automatically gathers operational and financial data from multiple sources, reconciles transactions, categorizes expenses, and generates accurate P&L reports and AI-powered business insights.

The platform is intended to become a complete restaurant financial operating system, not merely an OCR invoice application.

# CORE BUSINESS REQUIREMENTS

The platform must:

- Connect to Toast POS.
- Import and synchronize sales and labor data.
- Connect to Gmail and Outlook.
- Import invoices, bills, receipts, statements, and vendor documents.
- OCR all supported documents.
- Reconcile financial transactions.
- Categorize expenses.
- Generate P&L statements.
- Generate AI insights.
- Support multiple locations.
- Support multiple brands.
- Support custom date-range reporting.

Supported reporting periods:

- Daily
- Weekly
- Monthly
- Quarterly
- Yearly
- Custom date ranges

# TECHNOLOGY STACK

Frontend:
- Next.js App Router
- TypeScript
- Tailwind CSS
- shadcn/ui

Backend:
- FastAPI
- Python

Database:
- PostgreSQL
- pgvector

AI:
- Claude API

OCR:
- Google Document AI

Authentication:
- JWT
- RBAC

Deployment:
- Docker
- Docker Compose

# ENGINEERING PRINCIPLES

Claude must:

- Never make assumptions.
- Ask questions when requirements are ambiguous.
- Produce production-ready code only.
- Prefer correctness over speed.
- Generate complete implementations.
- Generate tests.
- Generate migrations.
- Consider security before coding.
- Consider scalability before coding.
- Consider observability before coding.
- Follow SOLID principles.
- Follow clean architecture.

# REQUIRED WORKFLOW

Before writing code:

1. Review requirements.
2. Identify missing information.
3. Identify risks.
4. Review architecture impact.
5. Review database impact.
6. Propose implementation plan.

After implementation:

1. Security review.
2. Edge case review.
3. Tenant isolation review.
4. Performance review.
5. Testing review.

# MULTI-TENANCY

Every table must contain tenant_id.

Requirements:

- Tenant isolation is mandatory.
- Every query must be tenant-scoped.
- Every API request must validate tenant ownership.
- Every report must be tenant-scoped.
- Every AI request must be tenant-scoped.

Cross-tenant data exposure is a critical defect.

# AUTHENTICATION & AUTHORIZATION

JWT claims:

- user_id
- tenant_id
- role

Roles:

- owner
- manager
- viewer

RBAC must be enforced on frontend and backend.

# TOAST INTEGRATION

Toast is the primary sales source.

Import:

- Sales
- Orders
- Menu items
- Categories
- Discounts
- Refunds
- Voids
- Taxes
- Labor
- Employees
- Time clock data

Requirements:

- Historical import
- Incremental sync
- Daily sync
- Manual sync
- Retry failed syncs

Never overwrite historical records.

# EMAIL SYNCHRONIZATION

Supported providers:

- Gmail
- Outlook / Microsoft 365

Daily batch jobs must:

- Scan inboxes
- Scan attachments
- Detect invoices
- Detect receipts
- Detect bills
- Detect vendor statements

Supported files:

- PDF
- PNG
- JPG
- JPEG
- TIFF

Duplicate detection required.

# GOOGLE DRIVE & ONEDRIVE

Daily synchronization required.

Import:

- Invoices
- Receipts
- Statements
- Financial documents

Incremental sync required.

# GOOGLE BUSINESS PROFILE

Import:

- Reviews
- Ratings
- Review counts
- Review trends

Store historical snapshots.

# GOOGLE ADS

Import:

- Campaigns
- Spend
- Impressions
- Clicks
- Conversions
- ROAS

Marketing spend must flow into P&L automatically.

# DOCUMENT PIPELINE

1. Upload or sync document.
2. Store original document.
3. Create document record.
4. OCR processing.
5. Store raw OCR response.
6. Extract structured data.
7. Categorize expenses.
8. Reconcile transactions.
9. Generate financial reports.
10. Generate AI insights.

Original files are immutable.

# OCR RULES

- Preserve originals.
- Store OCR responses.
- Store confidence scores.
- Support manual corrections.
- Support reprocessing.

# FINANCIAL DATA RULES

Never use floating point values for money.

Python:
- Decimal

PostgreSQL:
- NUMERIC(15,2)

Store:
- amount
- currency_code

All financial calculations must be deterministic.

Every financial record must include:

- tenant_id
- created_at
- updated_at
- created_by

# RECONCILIATION ENGINE

Automatically reconcile:

- Toast sales
- Invoices
- Receipts
- Bills
- Marketing spend

Flag:

- Missing invoices
- Duplicate invoices
- Duplicate receipts
- Uncategorized expenses
- Suspicious transactions

All reconciliation actions must be auditable.

# EXPENSE CATEGORIES

Support:

- Food Cost
- Beverage Cost
- Packaging
- Cleaning
- Utilities
- Rent
- Marketing
- Payroll
- Repairs
- Maintenance
- Insurance
- Software
- Professional Services
- Miscellaneous

AI may recommend categories.

Users may override categories.

# P&L ENGINE

Generate:

- Gross Revenue
- Net Revenue
- COGS
- Labor Cost
- Prime Cost
- Gross Profit
- EBITDA
- Net Profit

Support:

- Single location
- Multi-location
- Consolidated reporting

Reports must support any date range.

# AI RULES

AI may:

- Categorize expenses
- Detect anomalies
- Generate summaries
- Analyze trends

AI must never:

- Modify source financial records
- Change invoice values
- Override accounting calculations

Every AI output must include:

- confidence_score
- explanation

# API STANDARDS

- Use /api/v1
- Typed requests
- Typed responses
- Consistent error format

# SECURITY

Requirements:

- Input validation
- Upload validation
- Virus scanning
- Rate limiting
- Secret encryption
- Least privilege access

Never log:

- Passwords
- JWTs
- API keys
- Sensitive financial data

# OBSERVABILITY

Implement:

- Structured logging
- Audit logging
- Error monitoring
- Job monitoring
- Request tracing

# SCHEDULED JOBS

Daily:

- Toast sync
- Gmail sync
- Outlook sync
- Google Drive sync
- OneDrive sync
- OCR processing
- Reconciliation
- AI categorization

Weekly:

- Financial consistency checks

Monthly:

- P&L snapshots
- Executive summaries
- Trend analysis

Failed jobs must retry automatically.

# TESTING REQUIREMENTS

Every feature requires:

- Unit tests
- Integration tests
- Permission tests
- Tenant isolation tests
- Failure path tests

Coverage targets:

- Backend 90%+
- Critical finance logic 100%

# CODE QUALITY

TypeScript:

- strict mode
- no any

Python:

- Ruff
- Black
- Type hints

# ENVIRONMENT VARIABLES

- Never commit .env
- Commit .env.example
- Validate configuration at startup

# FUTURE INTEGRATIONS

Architecture must support:

- Uber Eats
- DoorDash
- SkipTheDishes
- QuickBooks
- PushOperations
- Bank feeds
- Payroll systems

Integrations must be provider-agnostic.

# DO NOT

- Hardcode secrets.
- Bypass RBAC.
- Bypass tenant filtering.
- Use floating point for money.
- Disable type checking.
- Use mock data in production.
- Trust AI output without validation.

When uncertain:

STOP.

Ask clarifying questions before implementation.