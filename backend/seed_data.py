"""
Seeds the database with:
  - The provided chart of accounts (Personal Services, MOOE, Capital Outlay,
    Financial Expenses)
  - The default admin account (Dher / Derps1216)

Run once: `python seed_data.py`
Safe to re-run -- it skips anything that already exists.
"""
from sqlalchemy import text, inspect
from database import SessionLocal, engine, Base
import models
from auth import hash_password


def ensure_new_columns():
    """create_all() only creates tables that don't exist yet -- it never
    alters an EXISTING table to add new columns. That's fine for a fresh
    local SQLite file (always rebuilt from scratch), but it's a real problem
    for a live production database (Neon) that already has real data in
    tables like 'offices' and 'proposals' from before these columns
    existed. This adds any missing columns safely, without touching
    existing data, and does nothing if they're already present (safe to
    run every deploy)."""
    inspector = inspect(engine)
    is_postgres = engine.dialect.name == "postgresql"
    blob_type = "BYTEA" if is_postgres else "BLOB"
    boolean_type = "BOOLEAN" if is_postgres else "INTEGER"
    existing_tables = inspector.get_table_names()

    with engine.begin() as conn:
        if "offices" in existing_tables:
            existing_cols = {c["name"] for c in inspector.get_columns("offices")}
            if "logo_data" not in existing_cols:
                conn.execute(text(f"ALTER TABLE offices ADD COLUMN logo_data {blob_type}"))
                print("Migration: added offices.logo_data")
            if "logo_content_type" not in existing_cols:
                conn.execute(text("ALTER TABLE offices ADD COLUMN logo_content_type VARCHAR"))
                print("Migration: added offices.logo_content_type")

        if "proposals" in existing_tables:
            existing_cols = {c["name"] for c in inspector.get_columns("proposals")}
            if "locked_by_admin" not in existing_cols:
                default_clause = "DEFAULT FALSE" if is_postgres else "DEFAULT 0"
                conn.execute(text(f"ALTER TABLE proposals ADD COLUMN locked_by_admin {boolean_type} NOT NULL {default_clause}"))
                print("Migration: added proposals.locked_by_admin")

# classification, code, name
ACCOUNTS = [
    # -------- Personal Services --------
    ("PS", "50101010", "Salaries & Wages-Regular"),
    ("PS", "50101010", "Salaries & Wages-Regular (Step Increment)"),
    ("PS", "50102010", "Personnel Economic Relief Allowance (PERA)"),
    ("PS", "50102020", "Representation Allowance (RA)"),
    ("PS", "50102030", "Transportation Allowance (TA)"),
    ("PS", "50102040", "Clothing/Uniform Allowance"),
    ("PS", "50102050", "Subsistence Allowance"),
    ("PS", "50102060", "Laundry Allowance"),
    ("PS", "50104990", "Productivity Enhancement Incentive (Other Personnel Benefits)"),
    ("PS", "50102100", "Honoraria"),
    ("PS", "50102110", "Hazard Pay"),
    ("PS", "50102120", "Longetivity Pay"),
    ("PS", "50102130", "Overtime and Night Pay"),
    ("PS", "50102140", "Year End Bonus"),
    ("PS", "50102150", "Cash Gift"),
    ("PS", "50102990", "Other Bonuses and Allowances (Mid-Year Bonus)"),
    ("PS", "50102990", "Other Bonuses and Allowances (Medical Allowance)"),
    ("PS", "50103010", "Retirement & Life Insurance Premiums"),
    ("PS", "50103020", "Pag-Ibig Contributions"),
    ("PS", "50103030", "PHILHEALTH Contributions"),
    ("PS", "50103040", "Employees Compensation Insurance Premiums"),
    ("PS", "50104030", "Terminal Leave Benefits"),
    ("PS", "50104990", "Other Personnel Benefits (Monetization)"),

    # -------- Maintenance and Other Operating Expenditures --------
    ("MOOE", "50201010", "Traveling Expenses-Local"),
    ("MOOE", "50201020", "Traveling Expenses-Foreign"),
    ("MOOE", "50202010", "Training Expenses"),
    ("MOOE", "50202020", "Scholarship Grants/Expenses"),
    ("MOOE", "50203010", "Office Supplies Expenses"),
    ("MOOE", "50203020", "Accountable Forms Expenses"),
    ("MOOE", "50203040", "Animal/Zoological Supplies Expenses"),
    ("MOOE", "50203050", "Food Supplies Expenses"),
    ("MOOE", "50203070", "Drugs and Medicines Expenses"),
    ("MOOE", "50203080", "Medical, Dental & Laboratory Supplies Expenses"),
    ("MOOE", "50203090", "Fuel, Oil & Lubricants Expenses"),
    ("MOOE", "50203100", "Agricultural & Marine Supplies Expenses"),
    ("MOOE", "50203110", "Textbooks and Instructional Materials Expenses"),
    ("MOOE", "50203120", "Military, Police & Traffic Supplies Expenses"),
    ("MOOE", "50203130", "Chemical and Filtering Supplies Expense"),
    ("MOOE", "50203210", "Semi-Expendable Machinery and Equipment Expenses"),
    ("MOOE", "50203220", "Semi-Expendable Furniture, Fixtures and Books Expenses"),
    ("MOOE", "50203990", "Other Supplies & Materials Expenses"),
    ("MOOE", "50204010", "Water Expenses"),
    ("MOOE", "50204020", "Electricity Expenses"),
    ("MOOE", "50205010", "Postage & Courier Services"),
    ("MOOE", "50205020", "Telephone Expenses"),
    ("MOOE", "50205030", "Internet Subscription Expenses"),
    ("MOOE", "50205040", "Cable, Satellite, Telegraph & Radio Expenses"),
    ("MOOE", "50206010", "Awards and Rewards Expenses"),
    ("MOOE", "50206020", "Prizes"),
    ("MOOE", "50207010", "Survey"),
    ("MOOE", "50207020", "Research, Exploration and Development Expenses"),
    ("MOOE", "50208010", "Demolition & Relocation Expense"),
    ("MOOE", "50210010", "Confidential Expenses"),
    ("MOOE", "50210020", "Intelligence Expense"),
    ("MOOE", "50210030", "Extraordinary and Miscellaneous Expenses"),
    ("MOOE", "50211020", "Auditing Services"),
    ("MOOE", "50211030", "Consultancy Services"),
    ("MOOE", "50211990", "Other Professional Services"),
    ("MOOE", "50212010", "Environment/Sanitary Services"),
    ("MOOE", "50212030", "Security Services"),
    ("MOOE", "50212990", "Other General Services"),
    ("MOOE", "50213020", "Repairs & Maintenance - Land Improvements"),
    ("MOOE", "50213030", "Repairs & Maintenance - Infrastructure Assets"),
    ("MOOE", "50213040", "Repairs & Maintenance - Buildings & Other Structures"),
    ("MOOE", "50213050", "Repairs & Maintenance - Machinery & Equipment"),
    ("MOOE", "50213060", "Repairs & Maintenance - Transportation Equipment"),
    ("MOOE", "50213070", "Repairs & Maintenance - Furniture & Fixtures"),
    ("MOOE", "50213210", "Repairs & Maintenance - Semi-Expendable Machinery and Equipment"),
    ("MOOE", "50213220", "Repairs & Maintenance - Semi-Expendable Furniture, Fixtures and Books"),
    ("MOOE", "50213990", "Repairs & Maint.-Other Property, Plant & Eqpt."),
    ("MOOE", "50214220", "Subsidy to NGA's"),
    ("MOOE", "50214030", "Subsidy to Other Local Government Units"),
    ("MOOE", "50214060", "Subsidy to Other Funds"),
    ("MOOE", "50214990", "Subsidies - Others"),
    ("MOOE", "50216010", "Taxes, Duties & Licenses"),
    ("MOOE", "50216020", "Fidelity Bond Premiums"),
    ("MOOE", "50216030", "Insurance Expenses"),
    ("MOOE", "50299010", "Advertising Expenses"),
    ("MOOE", "50299020", "Printing & Publication Expenses"),
    ("MOOE", "50299030", "Representation Expenses"),
    ("MOOE", "50299040", "Transportation & Delivery Expenses"),
    ("MOOE", "50299050", "Rent Expenses"),
    ("MOOE", "50299060", "Membership Dues and Contributions to Orgs."),
    ("MOOE", "50299070", "Subscription Expenses"),
    ("MOOE", "50299080", "Donation"),
    ("MOOE", "50299990", "Other Maintenance & Operating Expenses"),
    ("MOOE", "50301990", "Other Financial Charges"),

    # -------- Financial Expenses --------
    ("FE", "50301040", "Bank Charges"),

    # -------- Capital Outlay --------
    ("CO", "10701010", "Land"),
    ("CO", "10702010", "Land Improvements-Aquaculture Structures"),
    ("CO", "10702010", "Other Land Improvements"),
    ("CO", "10703040", "Water Supply Systems"),
    ("CO", "10703060", "Communication Networks"),
    ("CO", "10703990", "Other Infrastructure Assets"),
    ("CO", "10703090", "Plaza, Parks and Monuments"),
    ("CO", "10703010", "Road Networks"),
    ("CO", "10704010", "Buildings"),
    ("CO", "10704030", "Hospitals and Health Centers"),
    ("CO", "10704990", "Other Structures"),
    ("CO", "10705010", "Machinery"),
    ("CO", "10705020", "Office Equipment"),
    ("CO", "10705030", "Information & Communication Technology Eqpt."),
    ("CO", "10705040", "Agricultural & Forestry Equipment"),
    ("CO", "10705070", "Communication Equipment"),
    ("CO", "10705080", "Construction and Heavy Equipment"),
    ("CO", "10705090", "Disaster Response & Rescue Equipment"),
    ("CO", "10705100", "Military Police & Security Equipment"),
    ("CO", "10705110", "Medical Equipment"),
    ("CO", "10705120", "Printing Equipment"),
    ("CO", "10705130", "Sports Equipment"),
    ("CO", "10705140", "Technical and Scientific Equipment"),
    ("CO", "10705990", "Other Machinery and Equipment"),
    ("CO", "10706010", "Motor Vehicles"),
    ("CO", "10707010", "Furniture and Fixtures"),
    ("CO", "10707020", "Books"),
    ("CO", "10799010", "Work/Zoo Animals"),
    ("CO", "10799990", "Other Property, Plant & Equipment"),
    ("CO", "10801010", "Breeding Stocks"),
    ("CO", "10801020", "Plants and Trees"),
    ("CO", "10901020", "Computer Software"),
]


def run():
    ensure_new_columns()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Accounts
        existing = {(a.classification.value, a.code, a.name) for a in db.query(models.Account).all()}
        added = 0
        for classification, code, name in ACCOUNTS:
            if (classification, code, name) in existing:
                continue
            db.add(models.Account(classification=classification, code=code, name=name))
            added += 1
        db.commit()
        print(f"Accounts seeded: {added} added, {len(ACCOUNTS) - added} already present.")

        # Default admin
        admin = db.query(models.User).filter(models.User.username == "Dher").first()
        if not admin:
            db.add(models.User(
                username="Dher",
                password_hash=hash_password("Derps1216"),
                role=models.Role.admin,
                office_id=None,
            ))
            db.commit()
            print("Default admin user created: Dher")
        else:
            print("Default admin user already exists.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
