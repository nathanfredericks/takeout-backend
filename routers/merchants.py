from typing import List

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from db import SessionDep
from models import (
    Item,
    ItemCreateSchema,
    ItemReadSchema,
    Merchant,
    MerchantCreateSchema,
    MerchantReadSchema,
    MerchantUpdateSchema,
    MerchantWithItemsSchema,
    Order,
    OrderStatus,
    UserRole,
)
from routers.dependencies import (
    PartnerOrConsumerUser,
    PartnerUser,
    check_merchant_owner,
)

router = APIRouter(prefix="/api", tags=["merchants"])


@router.get("/merchants", response_model=List[MerchantReadSchema])
async def list_merchants(
    session: SessionDep,
    current_user: PartnerOrConsumerUser,
):
    query = select(Merchant)

    if current_user.role == UserRole.PARTNER:
        query = query.where(Merchant.partner_id == current_user.id)

    merchants = session.execute(query).scalars().all()
    return merchants


@router.post("/merchants", response_model=MerchantReadSchema)
async def create_merchant(
    merchant: MerchantCreateSchema, session: SessionDep, current_user: PartnerUser
):
    db_merchant = Merchant(**merchant.dict(), partner_id=current_user.id)
    session.add(db_merchant)
    session.commit()
    session.refresh(db_merchant)
    return db_merchant


@router.get("/merchants/{merchant_id}", response_model=MerchantWithItemsSchema)
async def get_merchant(merchant_id: int, session: SessionDep, _: PartnerOrConsumerUser):
    merchant = (
        session.execute(
            select(Merchant)
            .options(joinedload(Merchant.items))
            .where(Merchant.id == merchant_id)
        )
        .unique()
        .scalar_one_or_none()
    )

    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Merchant not found"
        )

    return merchant


@router.patch("/merchants/{merchant_id}", response_model=MerchantReadSchema)
async def update_merchant(
    merchant_id: int,
    merchant_update: MerchantUpdateSchema,
    session: SessionDep,
    current_user: PartnerUser,
):
    merchant = check_merchant_owner(merchant_id, session, current_user)

    for field, value in merchant_update.dict(exclude_unset=True).items():
        setattr(merchant, field, value)

    session.commit()
    session.refresh(merchant)
    return merchant


@router.get("/merchants/{merchant_id}/items", response_model=List[ItemReadSchema])
async def list_merchant_items(
    merchant_id: int, session: SessionDep, _: PartnerOrConsumerUser
):
    items = (
        session.execute(select(Item).where(Item.merchant_id == merchant_id))
        .scalars()
        .all()
    )
    return items


@router.post("/merchants/{merchant_id}/items", response_model=ItemReadSchema)
async def create_merchant_item(
    merchant_id: int,
    item: ItemCreateSchema,
    session: SessionDep,
    current_user: PartnerUser,
):
    check_merchant_owner(merchant_id, session, current_user)

    db_item = Item(**item.dict(), merchant_id=merchant_id)
    session.add(db_item)
    session.commit()
    session.refresh(db_item)
    return db_item


@router.get("/merchants/{merchant_id}/items/{item_id}", response_model=ItemReadSchema)
async def get_merchant_item(
    merchant_id: int, item_id: int, session: SessionDep, _: PartnerOrConsumerUser
):
    item = session.execute(
        select(Item).where(Item.id == item_id).where(Item.merchant_id == merchant_id)
    ).scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )

    return item


@router.patch("/merchants/{merchant_id}/items/{item_id}", response_model=ItemReadSchema)
async def update_merchant_item(
    merchant_id: int,
    item_id: int,
    item_update: ItemCreateSchema,
    session: SessionDep,
    current_user: PartnerUser,
):
    check_merchant_owner(merchant_id, session, current_user)

    item = session.execute(
        select(Item).where(Item.id == item_id).where(Item.merchant_id == merchant_id)
    ).scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )

    for field, value in item_update.dict().items():
        setattr(item, field, value)

    session.commit()
    session.refresh(item)
    return item


@router.delete("/merchants/{merchant_id}/items/{item_id}", status_code=204)
async def delete_merchant_item(
    merchant_id: int, item_id: int, session: SessionDep, current_user: PartnerUser
):
    check_merchant_owner(merchant_id, session, current_user)

    item = session.execute(
        select(Item).where(Item.id == item_id).where(Item.merchant_id == merchant_id)
    ).scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )

    from sqlalchemy import text

    from models import OrderItem

    order_items = (
        session.execute(select(OrderItem).where(OrderItem.item_id == item_id))
        .scalars()
        .all()
    )

    for order_item in order_items:
        session.delete(order_item)

    session.delete(item)
    session.commit()


@router.delete("/merchants/{merchant_id}", status_code=204)
async def delete_merchant(
    merchant_id: int, session: SessionDep, current_user: PartnerUser
):
    merchant = check_merchant_owner(merchant_id, session, current_user)

    active_orders_count = session.execute(
        select(func.count(Order.id))
        .where(Order.merchant_id == merchant_id)
        .where(
            Order.status.in_(
                [
                    OrderStatus.PENDING,
                    OrderStatus.ACCEPTED,
                    OrderStatus.READY_FOR_PICKUP,
                    OrderStatus.IN_TRANSIT,
                ]
            )
        )
    ).scalar_one()

    if active_orders_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete merchant with active orders",
        )

    session.delete(merchant)
    session.commit()
