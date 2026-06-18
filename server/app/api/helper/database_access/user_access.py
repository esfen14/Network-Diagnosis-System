import sqlalchemy  as sa
from app import db
from app.system_models import User



# =========== Get From Database ==============
def get_user_by_id(user_id: int):
    return db.session.get(User, user_id)

def get_user_by_email(user_email: str):
    return db.session.get(User, user_email)

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
    
def exists_email(email):
    return db.session.scalar(
            sa.select(
                sa.exists()
                .where(
                    User.Email == email
                )
            )
        )

