"""Demo data seeder — run `python -m app.seed` after first boot.
Creates users, four realistic enterprise documents (indexed through the real
RAG pipeline), a sample conversation, and memory entries."""
import os

from app.core.config import settings
from app.core.database import SessionLocal, init_db
from app.core.security import hash_password
from app.models import Conversation, Document, MemoryEntry, Message, User
from app.rag import pipeline

DOCS = {
    "HR_Leave_Policy.md": """# Horizon Corp — Leave & Attendance Policy
## Annual Leave
All full-time employees accrue 24 days of paid annual leave per calendar year, credited monthly at 2 days per month. Unused leave up to 10 days may be carried forward to the next year; the remainder lapses on 31 December.
## Sick Leave
Employees receive 12 days of paid sick leave annually. A medical certificate is required for absences longer than 2 consecutive days. Unused sick leave does not carry forward and is not encashable.
## Parental Leave
Maternity leave is 26 weeks fully paid. Paternity leave is 15 working days, usable within 6 months of the child's birth. Adoptive parents receive 12 weeks of paid leave.
## Work From Home
Employees may work remotely up to 3 days per week with manager approval. Fully remote arrangements require VP-level sign-off and are reviewed quarterly.
""",
    "Q3_Financial_Summary.md": """# Horizon Corp — Q3 FY2026 Financial Summary
## Revenue
Q3 revenue reached $48.2M, up 14% year-over-year, driven primarily by the Enterprise segment which grew 22% to $29.5M. SMB revenue was flat at $12.1M and Services contributed $6.6M.
## Costs & Margin
Gross margin improved to 71% from 68% last quarter due to cloud cost optimization that saved $1.8M. Operating expenses were $27.4M, with R&D at $11.2M (41% of opex).
## Outlook
Q4 guidance is $52-54M revenue with continued Enterprise momentum. Key risks: elongating sales cycles in EMEA and currency headwinds estimated at 1.5% of revenue.
""",
    "Atlas_Product_Manual.md": """# Atlas Platform — Administrator Manual
## Deployment
Atlas ships as Docker images. Minimum requirements: 4 vCPU, 16GB RAM, PostgreSQL 15+, and object storage (S3-compatible). High-availability mode requires 3 nodes behind a load balancer.
## User Roles
Atlas defines three roles: Admin (full control, billing, user management), Manager (team dashboards, report scheduling), and Member (personal workspace only). Role changes propagate within 60 seconds.
## Backup & Recovery
Automated backups run nightly at 02:00 UTC with 30-day retention. Point-in-time recovery is supported up to 7 days. To restore, run `atlasctl restore --timestamp <ISO8601>` from any admin node.
## API Rate Limits
The REST API allows 1,000 requests per minute per workspace. Webhook deliveries retry 5 times with exponential backoff starting at 30 seconds.
""",
    "Security_Incident_SOP.md": """# Security Incident Response SOP
## Severity Levels
SEV-1: active breach or data exfiltration — respond within 15 minutes, notify CISO immediately. SEV-2: vulnerability with exploit path — respond within 4 hours. SEV-3: policy violation or suspicious activity — respond within 1 business day.
## Response Steps
1. Contain: isolate affected systems from the network. 2. Assess: determine scope, systems, and data involved. 3. Eradicate: remove the threat and patch the entry vector. 4. Recover: restore from clean backups and monitor for 72 hours. 5. Review: blameless postmortem within 5 business days.
## Contacts
Security on-call: +1-555-0142 (24/7). CISO: security-leadership@horizon.example. Legal must be looped in for any incident involving personal data.
""",
}


def seed() -> None:
    init_db()
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    with SessionLocal() as db:
        # ── users ────────────────────────────────────────────────
        def ensure_user(email: str, name: str, role: str, hue: int, password: str = "demo12345") -> User:
            user = db.query(User).filter(User.email == email).first()
            if user is None:
                user = User(email=email, full_name=name, hashed_password=hash_password(password), role=role, avatar_hue=hue)
                db.add(user)
                db.commit()
                db.refresh(user)
            return user

        # Admin keeps the documented bootstrap password (admin12345), matching main.py
        admin = ensure_user("admin@eaios.dev", "System Administrator", "admin", 265, password="admin12345")
        maya = ensure_user("maya@eaios.dev", "Maya Iyer", "manager", 180)
        ensure_user("dev@eaios.dev", "Darshan Dalvi", "employee", 210)

        # ── documents through the real pipeline ──────────────────
        for filename, content in DOCS.items():
            if db.query(Document).filter(Document.filename == filename).first():
                continue
            doc = Document(
                filename=filename,
                title=filename.removesuffix(".md").replace("_", " "),
                doc_type="txt",
                owner_id=admin.id,
                status="queued",
                tags="seed,demo",
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)
            path = os.path.join(settings.UPLOAD_DIR, f"{doc.id}.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            doc.size_bytes = os.path.getsize(path)
            db.commit()
            pipeline.ingest_document(doc.id, path)

        # ── sample conversation ──────────────────────────────────
        if db.query(Conversation).count() == 0:
            conv = Conversation(user_id=maya.id, title="How many annual leave days do we get?")
            db.add(conv)
            db.commit()
            db.add_all([
                Message(conversation_id=conv.id, role="user", content="How many annual leave days do we get?"),
                Message(
                    conversation_id=conv.id, role="assistant", agent="document", confidence=88,
                    content="Based on the indexed enterprise documents: All full-time employees accrue 24 days of paid annual leave per calendar year, credited monthly at 2 days per month.",
                ),
            ])
            db.commit()

        # ── memory ───────────────────────────────────────────────
        if db.query(MemoryEntry).count() == 0:
            db.add_all([
                MemoryEntry(user_id=maya.id, kind="preference", content="Prefers executive summaries under 200 words"),
                MemoryEntry(user_id=maya.id, kind="project", content="Leading the Atlas HA deployment project (Q4)"),
            ])
            db.commit()

    print("Seed complete — login: admin@eaios.dev / admin12345 · maya@eaios.dev / demo12345")


if __name__ == "__main__":
    seed()
