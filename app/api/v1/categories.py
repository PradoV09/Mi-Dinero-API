from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_csrf
from app.core.errors import ApiError
from app.models import Category, User
from app.schemas.category import (
    CategoryCreate,
    CategoryListResponse,
    CategoryResponse,
    TransactionType,
)

router = APIRouter(prefix="/categories", tags=["categories"])


def _serialize(category: Category) -> CategoryResponse:
    return CategoryResponse(
        id=category.id,
        name=category.name,
        type=category.type,
        is_system=category.user_id is None,
    )


def _visible_to(user: User):
    return or_(Category.user_id.is_(None), Category.user_id == user.id)


@router.get("", response_model=CategoryListResponse)
async def list_categories(
    category_type: TransactionType | None = Query(None, alias="type"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CategoryListResponse:
    filters = [_visible_to(user)]
    if category_type is not None:
        filters.append(Category.type == category_type)

    total = await session.scalar(
        select(func.count()).select_from(Category).where(*filters)
    )
    categories = (
        await session.execute(
            select(Category)
            .where(*filters)
            .order_by(Category.type, Category.name, Category.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return CategoryListResponse(
        items=[_serialize(category) for category in categories],
        page=page,
        page_size=page_size,
        total=total or 0,
    )


@router.post("", status_code=201, response_model=CategoryResponse)
async def create_category(
    payload: CategoryCreate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_csrf),
) -> CategoryResponse:
    duplicate = await session.scalar(
        select(Category.id)
        .where(_visible_to(user))
        .where(Category.type == payload.type)
        .where(func.lower(Category.name) == payload.name.lower())
    )
    if duplicate is not None:
        raise ApiError(
            409,
            "category_name_taken",
            "Ya existe una categoria con ese nombre y tipo",
        )

    category = Category(user_id=user.id, type=payload.type, name=payload.name)
    session.add(category)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError(
            409,
            "category_name_taken",
            "Ya existe una categoria con ese nombre y tipo",
        ) from exc
    await session.refresh(category)
    return _serialize(category)
