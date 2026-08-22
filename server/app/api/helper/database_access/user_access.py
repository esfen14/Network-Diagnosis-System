import sqlalchemy  as sa
from app import db
from app.system_models import User



# =========== Get From Database ==============
def get_user_by_id(user_id: int):
    return db.session.get(User, user_id)

def get_user_by_email(user_email: str):
    return db.session.scalar(
        sa.select(User)
        .where(
            sa.func.lower(User.Email) == user_email.lower()
        )
    )

def get_all_users():
    return db.session.scalars(
        sa.select(User)
    ).all()

# =========== Check From Database =============
def exists_user_by_id(user_id):
    return db.session.scalar(
        sa.select(
            sa.exists()
            .where(
                User.UserID == user_id
            )
        )
    )
    
def exists_user_by_email(user_email):
    return  db.session.scalar(
        sa.select(
            sa.exists()
            .where(
                sa.func.lower(User.Email) == user_email.lower()
            )
        )
    )

def has_email(email, id):
    return db.session.scalar(
        sa.select(
            sa.exists()
            .where(
                sa.func.lower(User.Email) == email.lower(),
                User.UserID == id
            )
        )
    )