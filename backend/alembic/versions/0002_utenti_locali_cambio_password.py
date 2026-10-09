"""utenti locali: cambio password obbligatorio al primo accesso

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'utente',
        sa.Column('deve_cambiare_password', sa.Boolean(), server_default='false', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('utente', 'deve_cambiare_password')
