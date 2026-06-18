import sqlalchemy  as sa
from app import db
from app.system_models import Role

# ============= Get From Database ===================
def get_role_by_name(role_name: str):
    return db.session.get(Role, role_name)


def get_role_by_id(role_id: int):
    return db.session.get(Role, role_id)

# ============= Find From Database ===================
def exists_role_by_id(role_id):
    return db.session.scalar(
        sa.select(
            sa.exists()
            .where(
                Role.RoleID == role_id
            )
        )
    ) 

    
def exists_role_by_name(role_name):
    return db.session.scalar(
        sa.select(
            sa.exists()
            .where(
                sa.func.lower(Role.Name) == role_name.lower()
            )
        )
    ) 
    
