"""utenti: e-mail, codice di reset della password, verifica in due passaggi

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('utente', sa.Column('email', sa.String(length=254), nullable=True))
    op.add_column('utente', sa.Column('totp_segreto_cifrato', sa.Text(), nullable=True))
    op.add_column('utente', sa.Column('totp_attivo', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('utente', sa.Column('totp_ultimo_passo', sa.Integer(), nullable=True))
    op.add_column('utente', sa.Column('reset_codice_hash', sa.String(length=255), nullable=True))
    op.add_column('utente', sa.Column('reset_scadenza', sa.DateTime(timezone=True), nullable=True))
    op.add_column('utente', sa.Column('reset_tentativi', sa.Integer(), server_default='0', nullable=False))
    op.add_column('utente', sa.Column('reset_richiesto_il', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for colonna in ('reset_richiesto_il', 'reset_tentativi', 'reset_scadenza', 'reset_codice_hash',
                    'totp_ultimo_passo', 'totp_attivo', 'totp_segreto_cifrato', 'email'):
        op.drop_column('utente', colonna)
