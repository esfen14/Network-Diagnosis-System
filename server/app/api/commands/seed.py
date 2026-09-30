import sys

import click
import sqlalchemy as sa
from email_validator import validate_email, EmailNotValidError

from flask.cli import with_appcontext
from app import db
from app.api.helper.validation import STRONG_MIN_PASSWORD_LENGTH

from app.system_models import (
    Permission,
    Role,
    RolePermission,
    User,
    UserStatus,
    SystemSettings,
)

# =========================
# DATA DEFINITIONS
# =========================

PERMISSIONS = [
    "role.edit",
    "role.view",
    "role.info",
    "role.list",
    "account.view",
    "account.edit",
    "account.info",
    "system.discover",
    "system.deploy.ncpa",
    "system.hosts",
    "system.logs",
    "system.report",
    "system.notifications",
    "system.services",
    "system.network_health",
    "system.acknowledge_alerts",
    "system.dashboard",
    "plugin.scan",
    "plugin.view",
    "plugin.enable",
    "plugin.disable",
    "plugin.command_override",
    "plugin.command_restore",
    "plugin.validate",
    "plugin.custom_add",
    "plugin.update",
    "plugin.update_rollback",
    "plugin.configure",
    "settings.security",
    "settings.system",
    "settings.discovery",
]

ROLES = [
    ("Administrator", "System Administrator"),
    ("Manager", "Department Manager"),
    ("Staff", "Regular Staff"),
]

SEED_USERS = [
("Admin", "User", "admin@test.com", "Administrator", UserStatus.ACTIVE),
("John", "Doe", "john@test.com", "Manager", UserStatus.ACTIVE),
("Jane", "Smith", "jane@test.com", "Staff", UserStatus.INACTIVE),
("Michael", "Brown", "michael.brown@test.com", "Manager", UserStatus.ACTIVE),
("Emily", "Davis", "emily.davis@test.com", "Staff", UserStatus.ACTIVE),
("Daniel", "Wilson", "daniel.wilson@test.com", "Staff", UserStatus.ACTIVE),
("Sophia", "Taylor", "sophia.taylor@test.com", "Staff", UserStatus.ACTIVE),
("James", "Anderson", "james.anderson@test.com", "Manager", UserStatus.ACTIVE),
("Olivia", "Thomas", "olivia.thomas@test.com", "Staff", UserStatus.ACTIVE),
("William", "Jackson", "william.jackson@test.com", "Staff", UserStatus.ACTIVE),
("Ava", "White", "ava.white@test.com", "Staff", UserStatus.INACTIVE),
("Benjamin", "Harris", "benjamin.harris@test.com", "Manager", UserStatus.ACTIVE),
("Isabella", "Martin", "isabella.martin@test.com", "Staff", UserStatus.ACTIVE),
("Lucas", "Thompson", "lucas.thompson@test.com", "Staff", UserStatus.ACTIVE),
("Mia", "Garcia", "mia.garcia@test.com", "Staff", UserStatus.ACTIVE),
("Henry", "Martinez", "henry.martinez@test.com", "Manager", UserStatus.ACTIVE),
("Charlotte", "Robinson", "charlotte.robinson@test.com", "Staff", UserStatus.ACTIVE),
("Alexander", "Clark", "alexander.clark@test.com", "Staff", UserStatus.ACTIVE),
("Amelia", "Rodriguez", "amelia.rodriguez@test.com", "Staff", UserStatus.SUSPENDED),
("Ethan", "Lewis", "ethan.lewis@test.com", "Manager", UserStatus.ACTIVE),
("Harper", "Lee", "harper.lee@test.com", "Staff", UserStatus.ACTIVE),
("Mason", "Walker", "mason.walker@test.com", "Staff", UserStatus.ACTIVE),
("Evelyn", "Hall", "evelyn.hall@test.com", "Staff", UserStatus.ACTIVE),
("Logan", "Allen", "logan.allen@test.com", "Manager", UserStatus.ACTIVE),
("Abigail", "Young", "abigail.young@test.com", "Staff", UserStatus.ACTIVE),
("Elijah", "King", "elijah.king@test.com", "Staff", UserStatus.ACTIVE),
("Ella", "Wright", "ella.wright@test.com", "Staff", UserStatus.INACTIVE),
("Jacob", "Scott", "jacob.scott@test.com", "Manager", UserStatus.ACTIVE),
("Scarlett", "Green", "scarlett.green@test.com", "Staff", UserStatus.ACTIVE),
("Sebastian", "Baker", "sebastian.baker@test.com", "Staff", UserStatus.ACTIVE),
("Grace", "Adams", "grace.adams@test.com", "Staff", UserStatus.ACTIVE),
("Matthew", "Nelson", "matthew.nelson@test.com", "Manager", UserStatus.ACTIVE),
("Chloe", "Carter", "chloe.carter@test.com", "Staff", UserStatus.INACTIVE),
]


# =====================
# HELPERS
# =========================

def get_role(name: str):
    return db.session.scalar(
        sa.select(Role).where(Role.Name == name)
    )

def get_permission(name: str):
    return db.session.scalar(
        sa.select(Permission).where(Permission.Name == name)
    )

# =========================
# SEED: PERMISSIONS
# =========================

def seed_permissions():
    for name in PERMISSIONS:

        exists = db.session.scalar(
            sa.select(Permission).where(Permission.Name == name)
        )

        if exists:
            continue

        db.session.add(
            Permission(
                Name=name,
                Description=f"Permission for {name}"
            )
        )

    db.session.commit()


# =========================
# SEED: ROLES + ROLE PERMISSIONS
# =========================

def seed_roles():
    for name, desc in ROLES:

        role = get_role(name)

        if not role:
            role = Role(
                Name=name,
                Description=desc,
                Is_Active=True
            )
            db.session.add(role)
            db.session.flush()  # get RoleID

        # attach ALL permissions to Administrator only
        if name == "Administrator":
            for perm_name in PERMISSIONS:
                perm = get_permission(perm_name)
                if not perm:
                    continue

                exists = db.session.scalar(
                    sa.select(RolePermission).where(
                        RolePermission.RoleID == role.RoleID,
                        RolePermission.PermissionID == perm.PermissionID
                    )
                )

                if not exists:
                    db.session.add(
                        RolePermission(
                            RoleID=role.RoleID,
                            PermissionID=perm.PermissionID
                        )
                    )

    db.session.commit()


# =========================
# SEED: USERS
# =========================

def seed_users():
    for first, last, email, role_name, status in SEED_USERS:

        exists = db.session.scalar(
            sa.select(User).where(User.Email == email)
        )

        if exists:
            continue

        role = get_role(role_name)
        if not role:
            continue

        user = User(
            First_Name=first,
            Last_Name=last,
            Email=email,
            RoleID=role.RoleID,
            Status=status
        )

        user.set_password("Password123!")

        db.session.add(user)

    db.session.commit()


# =========================
# REMOVE SEED
# =========================

def remove_seed_data():

    # delete in correct FK order
    db.session.execute(sa.delete(RolePermission))
    db.session.execute(sa.delete(User))
    db.session.execute(sa.delete(Role))
    db.session.execute(sa.delete(Permission))

    db.session.commit()


# =========================
# CLI COMMAND
# =========================

@click.command("seed")
@click.option("--remove", is_flag=True, help="Remove seeded data")
@click.option("--permissions-only", is_flag=True, help="Seed only permissions")
@click.option("--reset", is_flag=True)
@with_appcontext
def seed_command(remove, permissions_only, reset):

    try:
        if reset:
            click.echo("Resetting DB...")
            
            db.drop_all()
            db.create_all()

            seed_permissions()
            seed_roles()
            seed_users()
        
        if remove:
            remove_seed_data()
            click.echo("✔ Seed data removed")
            return

        seed_permissions()

        if permissions_only:
            click.echo("✔ Permissions seeded only")
            return

        seed_roles()
        seed_users()

        click.echo("✔ Database seeded successfully")

    except Exception as e:
        db.session.rollback()
        click.echo(f"Seed failed: {e}")

    seed_system_settings()


# =========================
# SEED: SYSTEM SETTINGS
# =========================

def seed_system_settings():
    """Create the singleton SystemSettings row with defaults if it does not
    exist yet. Does not overwrite an existing row."""
    if db.session.get(SystemSettings, 1) is None:
        db.session.add(SystemSettings(Id=1))
        db.session.commit()


# =========================
# CLI COMMAND: PRODUCTION INIT
# =========================

@click.command("init-production")
@click.option("--admin-email", required=True, help="Email address of the administrator account.")
@click.option("--first-name", default="Admin", show_default=True)
@click.option("--last-name", default="User", show_default=True)
@click.option(
    "--password-stdin",
    is_flag=True,
    required=True,
    help="Read the administrator password from stdin (required).",
)
@with_appcontext
def init_production_command(admin_email, first_name, last_name, password_stdin):
    """
    Prepare a fresh production database: seed permissions, roles and system
    settings, then create a single active Administrator. No test users are
    created.

    The password is read from stdin only, never from an argument, so it does
    not appear in `ps` output or shell history:

        printf '%s' "$PASSWORD" | flask init-production --admin-email admin@pinpoint.lan --password-stdin

    Refuses to run if any user already exists, so re-running it during an
    upgrade cannot add a second administrator. Exits non-zero on any failure.
    """
    if not password_stdin:
        raise click.UsageError("--password-stdin is required.")

    # Only strip the line ending a shell pipe adds; other whitespace is
    # part of the password.
    password = sys.stdin.read().rstrip("\r\n")
    if len(password) < STRONG_MIN_PASSWORD_LENGTH:
        raise click.ClickException(
            f"Password must be at least {STRONG_MIN_PASSWORD_LENGTH} characters long."
        )

    try:
        admin_email = validate_email(admin_email, check_deliverability=False).normalized
    except EmailNotValidError as e:
        raise click.ClickException(f"Invalid admin email: {e}")

    user_count = db.session.scalar(sa.select(sa.func.count()).select_from(User))
    if user_count:
        raise click.ClickException(
            f"Refusing to initialise: {user_count} user(s) already exist."
        )

    try:
        seed_permissions()
        seed_roles()
        seed_system_settings()

        role = get_role("Administrator")
        if role is None:
            raise RuntimeError("Administrator role was not created.")

        admin = User(
            First_Name=first_name,
            Last_Name=last_name,
            Email=admin_email,
            RoleID=role.RoleID,
            Status=UserStatus.ACTIVE,
        )
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise click.ClickException(f"Production init failed: {e}")

    click.echo(f"Production database initialised with administrator {admin_email}")
