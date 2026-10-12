"""telefonia: token di Phone Island e dati SIP dell'utente, cifrati

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('utente', sa.Column('telefono_cifrato', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('utente', 'telefono_cifrato')
