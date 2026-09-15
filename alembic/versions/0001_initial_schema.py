"""Initial schema — all tables as of Step 9.

Revision ID: 0001
Revises: (none)
Create Date: 2026-09-15
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # locations
    # ------------------------------------------------------------------
    op.create_table(
        "locations",
        sa.Column("location_id", sa.String(12), primary_key=True, index=True),
        sa.Column("pincode", sa.String(10), nullable=False, index=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("radius_km", sa.Float(), nullable=False, default=20.0),
        sa.Column("district", sa.String(100), nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("tehsil", sa.String(100), nullable=True),
        sa.Column("anchor_name", sa.String(200), nullable=True),
        sa.Column("pin_basis", sa.String(50), nullable=True),
        sa.Column("coordinate_precision", sa.String(20), nullable=True),
        sa.Column("source_dataset", sa.String(50), nullable=False, default="geocoded_locations"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ------------------------------------------------------------------
    # categories
    # ------------------------------------------------------------------
    op.create_table(
        "categories",
        sa.Column("category_id", sa.String(12), primary_key=True, index=True),
        sa.Column("category_name", sa.String(200), nullable=False, unique=True),
        sa.Column("persona", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ------------------------------------------------------------------
    # jobs
    # ------------------------------------------------------------------
    op.create_table(
        "jobs",
        sa.Column("job_id", sa.String(16), primary_key=True, index=True),
        sa.Column("location_id", sa.String(12), sa.ForeignKey("locations.location_id"), nullable=False),
        sa.Column("category_id", sa.String(12), sa.ForeignKey("categories.category_id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, default="PENDING", index=True),
        sa.Column("search_query", sa.Text(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, default=0),
        sa.Column("max_retries", sa.Integer(), nullable=False, default=3),
        sa.Column("listings_found", sa.Integer(), nullable=True),
        sa.Column("businesses_saved", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("blocked_reason", sa.String(100), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ------------------------------------------------------------------
    # businesses
    # ------------------------------------------------------------------
    op.create_table(
        "businesses",
        sa.Column("business_id", sa.String(16), primary_key=True, index=True),
        sa.Column("job_id", sa.String(16), sa.ForeignKey("jobs.job_id"), nullable=False, index=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True, index=True),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("email_source_url", sa.String(500), nullable=True),
        sa.Column("email_enrichment_status", sa.String(100), nullable=True),
        sa.Column("email_enriched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("google_maps_url", sa.Text(), nullable=True),
        sa.Column("place_id", sa.String(100), nullable=True),
        sa.Column("category", sa.String(200), nullable=False, index=True),
        sa.Column("district", sa.String(100), nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("officename", sa.String(200), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("distance_km", sa.Float(), nullable=True),
        sa.Column("source_query", sa.Text(), nullable=False),
        sa.Column("dedup_key", sa.String(200), nullable=False, unique=True),
        sa.Column("is_valid", sa.Boolean(), nullable=False, default=True, index=True),
        sa.Column("validation_errors", sa.Text(), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ------------------------------------------------------------------
    # run_log
    # ------------------------------------------------------------------
    op.create_table(
        "run_log",
        sa.Column("run_id", sa.String(36), primary_key=True, index=True),
        sa.Column("trigger_source", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("jobs_attempted", sa.Integer(), nullable=False, default=0),
        sa.Column("jobs_completed", sa.Integer(), nullable=False, default=0),
        sa.Column("jobs_failed", sa.Integer(), nullable=False, default=0),
        sa.Column("jobs_total", sa.Integer(), nullable=False, default=0),
        sa.Column("jobs_retried", sa.Integer(), nullable=False, default=0),
        sa.Column("jobs_recovered", sa.Integer(), nullable=False, default=0),
        sa.Column("businesses_discovered", sa.Integer(), nullable=False, default=0),
        sa.Column("businesses_new", sa.Integer(), nullable=False, default=0),
        sa.Column("businesses_updated", sa.Integer(), nullable=False, default=0),
        sa.Column("businesses_duplicate", sa.Integer(), nullable=False, default=0),
        sa.Column("email_enriched", sa.Integer(), nullable=False, default=0),
        sa.Column("email_found", sa.Integer(), nullable=False, default=0),
        sa.Column("email_not_found", sa.Integer(), nullable=False, default=0),
        sa.Column("email_failed", sa.Integer(), nullable=False, default=0),
        sa.Column("errors_count", sa.Integer(), nullable=False, default=0),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Drop all tables in reverse dependency order."""
    op.drop_table("run_log")
    op.drop_table("businesses")
    op.drop_table("jobs")
    op.drop_table("categories")
    op.drop_table("locations")
