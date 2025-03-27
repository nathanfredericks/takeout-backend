from datetime import datetime, timezone
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from db import SessionDep
from models import (
    Item,
    Order,
    OrderCreateSchema,
    OrderItem,
    OrderReadSchema,
    OrderStatus,
    OrderStatusUpdateSchema,
    User,
    UserRole,
)
from routers.dependencies import (
    ConsumerUser,
    PartnerUser,
    check_merchant_owner,
    check_role,
)

router = APIRouter(prefix="/api", tags=["orders"])


@router.get("/orders", response_model=List[OrderReadSchema])
async def list_orders(
    session: SessionDep,
    current_user: Annotated[
        User, Depends(check_role(UserRole.CONSUMER, UserRole.COURIER))
    ],
):
    query = select(Order).options(
        joinedload(Order.items).joinedload(OrderItem.item),
        joinedload(Order.merchant),
        joinedload(Order.consumer),
        joinedload(Order.courier),
    )

    if current_user.role == UserRole.CONSUMER:
        query = query.where(Order.consumer_id == current_user.id)
    elif current_user.role == UserRole.COURIER:
        query = query.where(
            (Order.status == OrderStatus.READY_FOR_PICKUP)
            | (
                (Order.status.in_([OrderStatus.IN_TRANSIT, OrderStatus.DELIVERED]))
                & (Order.courier_id == current_user.id)
            )
        )

    result = session.execute(query).unique().scalars().all()
    orders = list(result)

    for order in orders:
        order.merchant_name = order.merchant.name
        order.merchant_location = order.merchant.location
        if order.courier:
            order.courier_name = order.courier.name

        total = sum(item.quantity * item.item.price for item in order.items)
        order.total = total

    return orders


@router.get("/orders/{order_id}", response_model=OrderReadSchema)
async def get_order(
    order_id: int,
    session: SessionDep,
    current_user: Annotated[
        User, Depends(check_role(UserRole.CONSUMER, UserRole.COURIER))
    ],
):
    query = (
        select(Order)
        .options(
            joinedload(Order.items).joinedload(OrderItem.item),
            joinedload(Order.merchant),
            joinedload(Order.consumer),
            joinedload(Order.courier),
        )
        .where(Order.id == order_id)
    )

    order = session.execute(query).unique().scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )

    if current_user.role == UserRole.CONSUMER:
        if order.consumer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Not your order"
            )
    elif current_user.role == UserRole.COURIER:
        if order.status == OrderStatus.READY_FOR_PICKUP:
            pass
        elif order.status in [OrderStatus.IN_TRANSIT, OrderStatus.DELIVERED]:
            if order.courier_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Order not available for viewing",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Order not available for viewing",
            )

    order.merchant_name = order.merchant.name
    order.merchant_location = order.merchant.location
    order.consumer_name = order.consumer.name
    if order.courier:
        order.courier_name = order.courier.name

    total = sum(item.quantity * item.item.price for item in order.items)
    order.total = total

    return order


@router.post("/merchants/{merchant_id}/orders", response_model=OrderReadSchema)
async def create_order(
    merchant_id: int,
    order: OrderCreateSchema,
    session: SessionDep,
    current_user: ConsumerUser,
):
    if not order.items or len(order.items) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order must contain at least one item",
        )

    for item in order.items:
        if item.quantity <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Item quantities must be positive",
            )

    item_ids = [item.item_id for item in order.items]
    items = (
        session.execute(
            select(Item)
            .where(Item.id.in_(item_ids))
            .where(Item.merchant_id == merchant_id)
        )
        .scalars()
        .all()
    )

    if len(items) != len(item_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One or more items not found or belong to different merchant",
        )

    db_order = Order(
        **order.dict(exclude={"items"}),
        merchant_id=merchant_id,
        consumer_id=current_user.id,
        status=OrderStatus.PENDING,
    )
    session.add(db_order)
    session.flush()

    for item_data in order.items:
        order_item = OrderItem(order_id=db_order.id, **item_data.dict())
        session.add(order_item)

    session.commit()

    db_order = (
        session.execute(
            select(Order)
            .options(
                joinedload(Order.items).joinedload(OrderItem.item),
                joinedload(Order.merchant),
                joinedload(Order.consumer),
            )
            .where(Order.id == db_order.id)
        )
        .unique()
        .scalar_one()
    )

    db_order.merchant_name = db_order.merchant.name
    db_order.merchant_location = db_order.merchant.location

    total = sum(item.quantity * item.item.price for item in db_order.items)
    db_order.total = total

    return db_order


@router.get(
    "/merchants/{merchant_id}/orders/{order_id}", response_model=OrderReadSchema
)
async def get_merchant_order(
    merchant_id: int, order_id: int, session: SessionDep, current_user: PartnerUser
):
    check_merchant_owner(merchant_id, session, current_user)

    order = (
        session.execute(
            select(Order)
            .options(
                joinedload(Order.items).joinedload(OrderItem.item),
                joinedload(Order.merchant),
                joinedload(Order.consumer),
                joinedload(Order.courier),
            )
            .where(Order.id == order_id)
            .where(Order.merchant_id == merchant_id)
        )
        .unique()
        .scalar_one_or_none()
    )

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )

    order.merchant_name = order.merchant.name
    order.merchant_location = order.merchant.location
    if order.courier:
        order.courier_name = order.courier.name

    total = sum(item.quantity * item.item.price for item in order.items)
    order.total = total

    return order


@router.get("/merchants/{merchant_id}/orders", response_model=List[OrderReadSchema])
async def list_merchant_orders(
    merchant_id: int,
    session: SessionDep,
    current_user: PartnerUser,
    status: OrderStatus | None = None,
):
    check_merchant_owner(merchant_id, session, current_user)

    query = (
        select(Order)
        .options(
            joinedload(Order.items).joinedload(OrderItem.item),
            joinedload(Order.merchant),
            joinedload(Order.consumer),
            joinedload(Order.courier),
        )
        .where(Order.merchant_id == merchant_id)
    )

    if status:
        query = query.where(Order.status == status)

    orders = session.execute(query).unique().scalars().all()

    for order in orders:
        order.merchant_name = order.merchant.name
        order.merchant_location = order.merchant.location
        order.consumer_name = order.consumer.name
        if order.courier:
            order.courier_name = order.courier.name

        total = sum(item.quantity * item.item.price for item in order.items)
        order.total = total

    return orders


@router.patch(
    "/merchants/{merchant_id}/orders/{order_id}", response_model=OrderReadSchema
)
async def update_order_status(
    merchant_id: int,
    order_id: int,
    status_update: OrderStatusUpdateSchema,
    session: SessionDep,
    current_user: Annotated[
        User, Depends(check_role(UserRole.CONSUMER, UserRole.PARTNER, UserRole.COURIER))
    ],
):
    order = (
        session.execute(
            select(Order)
            .options(
                joinedload(Order.items).joinedload(OrderItem.item),
                joinedload(Order.merchant),
                joinedload(Order.consumer),
                joinedload(Order.courier),
            )
            .where(Order.id == order_id)
            .where(Order.merchant_id == merchant_id)
        )
        .unique()
        .scalar_one_or_none()
    )

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )

    if current_user.role == UserRole.CONSUMER:
        if order.consumer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Not your order"
            )
    elif current_user.role == UserRole.PARTNER:
        _ = check_merchant_owner(merchant_id, session, current_user)
    elif current_user.role == UserRole.COURIER:
        if order.courier_id and order.courier_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Order already assigned to another courier",
            )

        if status_update.status == OrderStatus.IN_TRANSIT:
            active_orders = (
                session.execute(
                    select(Order)
                    .where(Order.courier_id == current_user.id)
                    .where(Order.status == OrderStatus.IN_TRANSIT)
                )
                .scalars()
                .all()
            )

            if active_orders:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You already have an active order in transit. Please deliver it before picking up a new order.",
                )

    if not order.status.can_transition_to(status_update.status, current_user.role):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot transition from {order.status} to {status_update.status} as {current_user.role}",
        )

    order.status = status_update.status

    if current_user.role == UserRole.COURIER:
        if status_update.status == OrderStatus.IN_TRANSIT and not order.courier_id:
            order.courier_id = current_user.id
        elif status_update.status == OrderStatus.DELIVERED:
            order.delivered_at = datetime.now(timezone.utc)

    session.commit()

    if (
        current_user.role == UserRole.COURIER
        and status_update.status == OrderStatus.IN_TRANSIT
    ):
        order = (
            session.execute(
                select(Order)
                .options(
                    joinedload(Order.items).joinedload(OrderItem.item),
                    joinedload(Order.merchant),
                    joinedload(Order.consumer),
                    joinedload(Order.courier),
                )
                .where(Order.id == order_id)
            )
            .unique()
            .scalar_one()
        )

    order.merchant_name = order.merchant.name
    order.merchant_location = order.merchant.location

    if order.courier:
        order.courier_name = order.courier.name

    total = sum(item.quantity * item.item.price for item in order.items)
    order.total = total

    return order
