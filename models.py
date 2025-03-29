from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel
from sqlalchemy import FLOAT, Column, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class UserRole(str, Enum):
    CONSUMER = "consumer"
    PARTNER = "partner"
    COURIER = "courier"


class OrderFilter(str, Enum):
    READY_FOR_PICKUP = "ready_for_pickup"
    IN_PROGRESS = "in_progress"
    DELIVERED = "delivered"
    ALL = "all"


class OrderStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    READY_FOR_PICKUP = "ready_for_pickup"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

    def can_transition_to(self, new_status: "OrderStatus", role: UserRole) -> bool:
        if role == UserRole.CONSUMER:
            valid_transitions = {OrderStatus.PENDING: [OrderStatus.CANCELLED]}
        elif role == UserRole.PARTNER:
            valid_transitions = {
                OrderStatus.PENDING: [
                    OrderStatus.ACCEPTED,
                    OrderStatus.CANCELLED,
                ],
                OrderStatus.ACCEPTED: [
                    OrderStatus.READY_FOR_PICKUP,
                    OrderStatus.CANCELLED,
                ],
                OrderStatus.READY_FOR_PICKUP: [OrderStatus.CANCELLED],
            }
        elif role == UserRole.COURIER:
            valid_transitions = {
                OrderStatus.READY_FOR_PICKUP: [OrderStatus.IN_TRANSIT],
                OrderStatus.IN_TRANSIT: [OrderStatus.DELIVERED],
            }
        else:
            return False

        return new_status in valid_transitions.get(self, [])


class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    phone_number = Column(String(50), nullable=False)
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.CONSUMER)
    password = Column(String(255), nullable=False)

    merchants = relationship("Merchant", back_populates="partner")
    orders_as_consumer = relationship("Order", foreign_keys="Order.consumer_id")
    orders_as_courier = relationship("Order", foreign_keys="Order.courier_id")


class Merchant(Base):
    __tablename__ = "merchant"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=True)
    location = Column(String(255), nullable=False)
    partner_id = Column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )

    items = relationship("Item", back_populates="merchant")
    orders = relationship("Order", back_populates="merchant")
    partner = relationship("User", back_populates="merchants")


class OrderItem(Base):
    __tablename__ = "order_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(Integer, ForeignKey("item.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, nullable=False)
    order_id = Column(
        Integer, ForeignKey("order.id", ondelete="CASCADE"), nullable=False
    )

    order = relationship("Order", back_populates="items")
    item = relationship("Item", back_populates="order_items")


class Order(Base):
    __tablename__ = "order"

    id = Column(Integer, primary_key=True, autoincrement=True)
    delivery_address = Column(String(255), nullable=False)
    order_instructions = Column(String(1000), nullable=True)
    merchant_id = Column(
        Integer, ForeignKey("merchant.id", ondelete="CASCADE"), nullable=False
    )
    consumer_id = Column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    courier_id = Column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=True
    )
    status = Column(SAEnum(OrderStatus), nullable=False, default=OrderStatus.PENDING)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    items = relationship("OrderItem", back_populates="order")
    merchant = relationship("Merchant", back_populates="orders")
    consumer = relationship("User", foreign_keys=[consumer_id])
    courier = relationship("User", foreign_keys=[courier_id])


class Item(Base):
    __tablename__ = "item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=True)
    price = Column(FLOAT, nullable=False)
    merchant_id = Column(
        Integer, ForeignKey("merchant.id", ondelete="CASCADE"), nullable=False
    )

    order_items = relationship("OrderItem", back_populates="item")
    merchant = relationship("Merchant", back_populates="items")


class UserBaseSchema(BaseModel):
    name: str
    email: str
    phone_number: str
    role: UserRole = UserRole.CONSUMER


class UserCreateSchema(UserBaseSchema):
    password: str


class UserReadSchema(UserBaseSchema):
    id: int

    class Config:
        from_attributes = True


class MerchantBaseSchema(BaseModel):
    name: str
    description: Optional[str] = None
    location: str


class MerchantCreateSchema(MerchantBaseSchema):
    pass


class MerchantReadSchema(MerchantBaseSchema):
    id: int
    partner_id: int

    class Config:
        from_attributes = True


class MerchantUpdateSchema(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None


class ItemBaseSchema(BaseModel):
    name: str
    description: Optional[str] = None
    price: float


class ItemCreateSchema(ItemBaseSchema):
    pass


class ItemReadSchema(ItemBaseSchema):
    id: int
    merchant_id: int

    class Config:
        from_attributes = True


class MerchantWithItemsSchema(MerchantReadSchema):
    items: List[ItemReadSchema]

    class Config:
        from_attributes = True


class OrderItemBaseSchema(BaseModel):
    item_id: int
    quantity: int


class OrderItemCreateSchema(OrderItemBaseSchema):
    pass


class OrderItemReadSchema(OrderItemBaseSchema):
    id: int
    item: ItemReadSchema

    class Config:
        from_attributes = True


class OrderBaseSchema(BaseModel):
    delivery_address: str
    order_instructions: Optional[str] = None


class OrderCreateSchema(OrderBaseSchema):
    items: List[OrderItemCreateSchema] = []


class OrderReadSchema(OrderBaseSchema):
    id: int
    merchant_id: int
    merchant_name: str
    merchant_location: str
    consumer_id: int
    consumer_name: str
    consumer_phone_number: str
    courier_id: Optional[int] = None
    courier_name: Optional[str] = None
    courier_phone_number: Optional[str] = None
    status: OrderStatus
    created_at: datetime
    delivered_at: Optional[datetime] = None
    items: List[OrderItemReadSchema]
    total: Optional[float] = None

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginSchema(BaseModel):
    email: str
    password: str


class OrderStatusUpdateSchema(BaseModel):
    status: OrderStatus
