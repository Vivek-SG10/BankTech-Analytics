import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether

PDF_PATH = r"D:\BankTech-Analytics\BankTech_Analytics_Project_Defense_Guide.pdf"

def generate():
    doc = SimpleDocTemplate(
        PDF_PATH,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=colors.HexColor('#1E3A8A'),
        spaceAfter=6,
    )
    
    meta_style = ParagraphStyle(
        'DocMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#64748B'),
        spaceAfter=14,
    )
    
    h1_style = ParagraphStyle(
        'SectionH1',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=17,
        textColor=colors.HexColor('#1E40AF'),
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True,
    )
    
    h2_style = ParagraphStyle(
        'SectionH2',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor('#0F172A'),
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True,
    )
    
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#334155'),
        spaceAfter=6,
    )
    
    body_bold = ParagraphStyle(
        'BodyBold',
        parent=body_style,
        fontName='Helvetica-Bold',
    )
    
    pitch_style = ParagraphStyle(
        'PitchText',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor('#1E3A8A'),
    )
    
    table_cell = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#1E293B'),
    )
    
    table_header = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#0F172A'),
    )

    story = []

    # Title & Metadata
    story.append(Paragraph("BankTech Analytics", title_style))
    story.append(Paragraph("Academic Project Defense & Comprehensive Technical Architecture Guide &bull; 2026", meta_style))
    story.append(Spacer(1, 4))

    # 1. Elevator Pitch Box
    pitch_data = [[
        Paragraph(
            "<b>The 30-Second Elevator Pitch:</b><br/>"
            "\"Respected panel members, banking institutions are undergoing rapid digital transformation, but measuring "
            "the actual impact of FinTech on human stakeholders remains a challenge. We built <b>BankTech Analytics</b> &mdash; "
            "a full-stack, research-driven banking analytics platform.<br/><br/>"
            "It implements validated psychometric instruments to collect structured feedback from three distinct stakeholder groups: "
            "<b>Employees</b>, <b>Managers</b>, and <b>Customers</b>. The platform computes four standardized indices: "
            "<b>Technology Adoption Index (TAI)</b>, <b>Employee Job Satisfaction Index (EJSI)</b>, <b>Employee Performance Index (EPI)</b>, "
            "and <b>Customer Service Effectiveness Index (CSEI)</b>.<br/><br/>"
            "The backend conducts automated statistical validation including <b>Cronbach's Alpha</b> for internal reliability, "
            "<b>Pearson correlation</b>, and <b>OLS regression</b>, while strictly preserving stakeholder anonymity using role-based access control (RBAC).\"",
            pitch_style
        )
    ]]
    pitch_table = Table(pitch_data, colWidths=[515])
    pitch_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#EFF6FF')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#3B82F6')),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(pitch_table)
    story.append(Spacer(1, 10))

    # 2. System Architecture Table
    story.append(Paragraph("1. System Architecture & Tech Stack", h1_style))
    arch_data = [
        [Paragraph("Layer", table_header), Paragraph("Technologies", table_header), Paragraph("Key Responsibilities & Capabilities", table_header)],
        [Paragraph("<b>Frontend SPA</b>", table_cell), Paragraph("React 19, TypeScript, Tailwind CSS 4, Vite 8", table_cell), Paragraph("Modular SPA, dynamic role-based surveys, interactive analytics dashboard, client RBAC route guards.", table_cell)],
        [Paragraph("<b>Backend API</b>", table_cell), Paragraph("FastAPI, Python 3.12, Pydantic 2, JWT, Bcrypt", table_cell), Paragraph("High-concurrency async REST API, OAuth2 Bearer JWT auth, automated OpenAPI/Swagger documentation.", table_cell)],
        [Paragraph("<b>Analytics Engine</b>", table_cell), Paragraph("Pandas, NumPy, SciPy, Scikit-Learn", table_cell), Paragraph("Index calculation, Cronbach's &alpha; reliability analysis, Pearson correlations, OLS regressions.", table_cell)],
        [Paragraph("<b>Persistence & ORM</b>", table_cell), Paragraph("SQLAlchemy 2.0 (Async), SQLite / PostgreSQL, Alembic", table_cell), Paragraph("Asynchronous engine, connection pooling, vote de-duplication/voiding, schema migrations.", table_cell)],
    ]
    arch_table = Table(arch_data, colWidths=[95, 140, 280])
    arch_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F1F5F9')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(arch_table)
    story.append(Spacer(1, 10))

    # 3. Incremental File Walkthrough
    story.append(Paragraph("2. Incremental File-by-File Walkthrough", h1_style))

    # Layer 1
    story.append(Paragraph("Layer 1: Core Configuration & Bootstrap", h2_style))
    files_l1 = [
        ("backend/app/core/config.py", "Centralizes environment variables with Pydantic Settings (BaseSettings). Reads .env for database credentials, JWT secrets, port configs, and CORS origins. Automatically normalizes driver schemes (psycopg3/aiosqlite). Adheres to 12-Factor App design."),
        ("backend/app/core/database.py", "Asynchronous database session factory using SQLAlchemy 2.0 async engine. Supplies get_db() dependency injector for routes (auto commit/rollback). Houses ping_database() for lightweight live health probe (SELECT 1)."),
        ("backend/app/main.py", "FastAPI entry point. Implements async lifespan context creating tables on startup (Base.metadata.create_all), CORSMiddleware, and registers modular routers: /health, /auth, /dev, /surveys, and /analytics."),
    ]
    for fn, desc in files_l1:
        story.append(Paragraph(f"&bull; <b><font color='#1E40AF'>{fn}</font></b> &mdash; {desc}", body_style))

    # Layer 2
    story.append(Paragraph("Layer 2: Security & Authentication (RBAC)", h2_style))
    files_l2 = [
        ("backend/app/auth/models.py", "Declares UserOrm table: UUID primary key, indexed unique email, bcrypt hashed_password (never plaintext), role identifier (admin, researcher, manager, employee, customer), and department affiliation."),
        ("backend/app/auth/security.py", "Provides hash_password() and verify_password() using bcrypt with randomized salt. Generates signed JWTs (HS256) encoding User ID, role, and expiration timestamp."),
        ("backend/app/auth/deps.py", "Authentication dependencies. get_current_user() decodes Bearer token from headers. require_roles(*roles) enforces Role-Based Access Control, returning 403 Forbidden on unauthorized attempts."),
        ("backend/app/auth/router.py & seed.py", "Exposes /register, /login, /me, and admin role assignment. seed.py creates 5 pre-configured demo stakeholder accounts for instant testing."),
    ]
    for fn, desc in files_l2:
        story.append(Paragraph(f"&bull; <b><font color='#1E40AF'>{fn}</font></b> &mdash; {desc}", body_style))

    story.append(PageBreak())

    # Layer 3
    story.append(Paragraph("Layer 3: Surveys & The Research Analytics Engine", h2_style))
    files_l3 = [
        ("backend/app/surveys/models.py", "Defines 3 distinct schemas: EmployeeSurveyOrm (TAI 1-5, EJSI 1-6, EPI-Self 1-3), ManagerSurveyOrm (TAI-Mgr 1-3, EPI-Mgr 1-4, branch operational KPIs), and CustomerSurveyOrm (channel, service type, CSEI 1-6). Includes SQL CheckConstraints (1-5 Likert). Contains zero PII."),
        ("backend/app/surveys/crud.py", "Survey persistence layer. Implements automated de-duplication: upon receiving a resubmission, updates is_voided=True on previous responses by that respondent so longitudinal analytics evaluate only the latest active response."),
        ("backend/app/analytics/indices.py", "Core quantitative mathematical engine:<br/>"
         "1. <b>Index Normalization:</b> Projects Likert means onto 0-100 scale: <i>Score = (Mean Raw / 5) &times; 100</i>.<br/>"
         "2. <b>Cronbach's Alpha (&alpha;):</b> Evaluates scale internal consistency: <i>&alpha; = [k/(k-1)] &times; [1 - (&Sigma;&sigma;<sub>i</sub><sup>2</sup> / &sigma;<sub>total</sub><sup>2</sup>)]</i> (&ge; 0.70 benchmark).<br/>"
         "3. <b>Statistical Privacy Suppression:</b> Enforces k-anonymity; withholds indices when N &lt; 5 to prevent individual re-identification. Correlations require N &ge; 10, regressions require N &ge; 20.<br/>"
         "4. <b>Inferential Statistics:</b> Computes Pearson correlation matrix and OLS linear regressions evaluating whether technology adoption significantly predicts employee performance."),
        ("backend/app/analytics/router.py", "Restricted endpoints for researchers/admins: /analytics/summary, /tai, /ejsi, /epi, /csei, /correlations, /regression, and /export/csv with academic privacy headers."),
    ]
    for fn, desc in files_l3:
        story.append(Paragraph(f"&bull; <b><font color='#1E40AF'>{fn}</font></b> &mdash; {desc}", body_style))

    # Layer 4
    story.append(Paragraph("Layer 4: Frontend Architecture (React 19 + TypeScript)", h2_style))
    files_l4 = [
        ("frontend/src/context/AuthContext.tsx", "Global React authentication state. Restores token from localStorage on reload, verifies validity against /auth/me, exposes login(), logout(), and hasRole() helpers."),
        ("frontend/src/components/RouteGuards.tsx", "Client-side route security: ProtectedRoute verifies role authorization (redirects unauthorized users to /forbidden); PublicOnlyRoute redirects logged-in users away from /login."),
        ("frontend/src/pages/ (Landing, Survey, Analytics)", "LandingPage.tsx presents research context; SurveyPage.tsx dynamically renders tailored Likert surveys per role; AnalyticsPage.tsx visualizes gauges, &alpha; indicators, and regression tables."),
    ]
    for fn, desc in files_l4:
        story.append(Paragraph(f"&bull; <b><font color='#1E40AF'>{fn}</font></b> &mdash; {desc}", body_style))

    # 4. Top Panel Questions & Answers
    story.append(Spacer(1, 6))
    story.append(Paragraph("3. Top Panel / Viva Defense Questions", h1_style))
    
    qa_list = [
        ("Q1: Why did you choose FastAPI over traditional Django or Flask?",
         "FastAPI operates on ASGI with native async Python type hints, enabling non-blocking concurrent I/O with SQLAlchemy 2.0 async. It performs automatic schema validation through Pydantic and automatically generates interactive OpenAPI/Swagger documentation."),
        ("Q2: Why are Employee Performance (EPI-Self) and Manager Performance (EPI-Manager) kept separate?",
         "In organizational psychology, self-reported performance is prone to self-serving bias (individuals over-estimating their performance). Keeping them separate preserves research validity: managers evaluate team-level metrics, while employees report individual engagement."),
        ("Q3: How is participant privacy and research ethics preserved?",
         "1) Zero PII (names, emails) is stored in survey tables. 2) Responses are bound only to anonymous UUIDs and branch departments. 3) The analytics engine enforces an automated suppression threshold (N &lt; 5) to prevent deductive re-identification."),
        ("Q4: What is Cronbach's Alpha and what does it measure?",
         "Cronbach's Alpha measures internal consistency—testing whether the multi-item questions intended to measure the same construct (e.g. ease of use in TAI) yield coherent scores. A value &alpha; &ge; 0.70 confirms the psychometric scale is statistically reliable."),
    ]
    for q, a in qa_list:
        story.append(Paragraph(f"<b>{q}</b>", ParagraphStyle('QStyle', parent=body_style, textColor=colors.HexColor('#1E3A8A'))))
        story.append(Paragraph(f"<b>Answer:</b> \"{a}\"", body_style))
        story.append(Spacer(1, 2))

    # 5. Demo Accounts Table
    story.append(Spacer(1, 4))
    story.append(Paragraph("4. Pre-Seeded Demo Accounts for Live Presentation", h1_style))
    demo_data = [
        [Paragraph("Role", table_header), Paragraph("Email Address", table_header), Paragraph("Password", table_header), Paragraph("Target Landing & Capabilities", table_header)],
        [Paragraph("<b>Admin</b>", table_cell), Paragraph("admin@banktech.dev", table_cell), Paragraph("Demo1234!", table_cell), Paragraph("Full system access, user role management, analytics dashboard.", table_cell)],
        [Paragraph("<b>Researcher</b>", table_cell), Paragraph("researcher@banktech.dev", table_cell), Paragraph("Demo1234!", table_cell), Paragraph("Analytics dashboard, Cronbach &alpha;, correlation/regression, CSV export.", table_cell)],
        [Paragraph("<b>Manager</b>", table_cell), Paragraph("manager@banktech.dev", table_cell), Paragraph("Demo1234!", table_cell), Paragraph("Manager survey submission, team operational KPIs report.", table_cell)],
        [Paragraph("<b>Employee</b>", table_cell), Paragraph("employee@banktech.dev", table_cell), Paragraph("Demo1234!", table_cell), Paragraph("Technology adoption (TAI) & job satisfaction (EJSI) survey.", table_cell)],
        [Paragraph("<b>Customer</b>", table_cell), Paragraph("customer@banktech.dev", table_cell), Paragraph("Demo1234!", table_cell), Paragraph("Customer service effectiveness (CSEI) survey submission.", table_cell)],
    ]
    demo_table = Table(demo_data, colWidths=[75, 135, 75, 230])
    demo_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F1F5F9')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(demo_table)

    doc.build(story)
    print("PDF build complete:", PDF_PATH)

if __name__ == '__main__':
    generate()

