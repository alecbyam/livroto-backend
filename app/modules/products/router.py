from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import uuid

from app.database import get_db
from app.dependencies import get_current_user, get_current_tenant
from app.core.rbac import Role, require_min_role
from app.core.exceptions import NotFoundError
from app.modules.products.models import Product, Category
from app.modules.products.schemas import ProductCreate, ProductUpdate, ProductResponse

router = APIRouter()


@router.get("/", response_model=list[ProductResponse])
async def list_products(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = None,
    category_id: uuid.UUID | None = None,
    in_stock: bool | None = None,
    tenant=Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    query = select(Product).where(
        Product.tenant_id == tenant.id,
        Product.is_active == True,
    )
    if search:
        query = query.where(Product.name.ilike(f"%{search}%"))
    if category_id:
        query = query.where(Product.category_id == category_id)
    if in_stock is True:
        query = query.where(Product.stock_qty > 0)

    query = query.offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: uuid.UUID,
    tenant=Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.tenant_id == tenant.id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise NotFoundError("Produit")
    return product


@router.post("/", response_model=ProductResponse, status_code=201)
async def create_product(
    body: ProductCreate,
    tenant=Depends(get_current_tenant),
    current_user=Depends(require_min_role(Role.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    product = Product(tenant_id=tenant.id, **body.model_dump())
    db.add(product)
    await db.flush()
    return product


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: uuid.UUID,
    body: ProductUpdate,
    tenant=Depends(get_current_tenant),
    current_user=Depends(require_min_role(Role.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.tenant_id == tenant.id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise NotFoundError("Produit")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(product, field, value)
    return product


@router.delete("/{product_id}", status_code=204)
async def delete_product(
    product_id: uuid.UUID,
    tenant=Depends(get_current_tenant),
    current_user=Depends(require_min_role(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.tenant_id == tenant.id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise NotFoundError("Produit")
    product.is_active = False  # Soft delete


@router.get("/alerts/low-stock", summary="Produits en stock critique")
async def low_stock_alert(
    tenant=Depends(get_current_tenant),
    current_user=Depends(require_min_role(Role.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Product).where(
            Product.tenant_id == tenant.id,
            Product.is_active == True,
            Product.stock_qty <= Product.stock_alert,
        )
    )
    products = result.scalars().all()
    return {
        "count": len(products),
        "products": [{"id": str(p.id), "name": p.name, "stock": p.stock_qty, "alert": p.stock_alert} for p in products],
    }
