from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.db.models import Workspace

COMPANY_WORKSPACE_SLUG = "company-root"


async def get_or_create_company_workspace(db: AsyncSession) -> Workspace:
    """Return the one hidden company boundary used by this single-company app."""
    company = (
        await db.execute(
            select(Workspace).where(
                Workspace.type == "organization",
                Workspace.slug == COMPANY_WORKSPACE_SLUG,
            )
        )
    ).scalar_one_or_none()
    if company is not None:
        return company

    company = Workspace(
        type="organization",
        name=get_settings().company_name.strip() or "Company",
        slug=COMPANY_WORKSPACE_SLUG,
        status="active",
    )
    try:
        async with db.begin_nested():
            db.add(company)
            await db.flush()
        return company
    except IntegrityError:
        # A concurrent first request may have created the singleton after our
        # initial SELECT. The unique slug is the final source of truth.
        return (
            await db.execute(
                select(Workspace).where(
                    Workspace.type == "organization",
                    Workspace.slug == COMPANY_WORKSPACE_SLUG,
                )
            )
        ).scalar_one()
