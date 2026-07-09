import click
import sqlalchemy as sa

from flask.cli import with_appcontext
from app import db

from app.system_models import (
    Permission,
    Role,
    RolePermission,
    User,
    UserStatus
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
]

ROLES = [
    ("Administrator", "System Administrator"),
    ("Manager", "Department Manager"),
    ("Staff", "Regular Staff"),
]

SEED_USERS = [
("Admin", "User", "[admin@test.com](mailto:admin@test.com)", "Administrator", UserStatus.ACTIVE),

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
("Chloe", "Carter", "chloe.carter@test.com", "Staff", UserStatus.ACTIVE),
]


# =========================
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
            First_name=first,
            Last_name=last,
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
        click.echo(f"❌ Seed failed: {e}")