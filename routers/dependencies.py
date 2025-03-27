from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select

from auth import CurrentUser
from db import SessionDep
from models import Merchant, User, UserRole


def check_role(*allowed_roles: UserRole):
    def role_checker(user: CurrentUser):
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted for this role",
            )
        return user

    return role_checker


def check_merchant_owner(merchant_id: int, session: SessionDep, user: CurrentUser):
    if user.role != UserRole.PARTNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only partners can access merchant management",
        )

    merchant = session.execute(
        select(Merchant).where(Merchant.id == merchant_id)
    ).scalar_one_or_none()

    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Merchant not found"
        )

    if merchant.partner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to manage this merchant",
        )

    return merchant


ConsumerUser = Annotated[User, Depends(check_role(UserRole.CONSUMER))]
PartnerUser = Annotated[User, Depends(check_role(UserRole.PARTNER))]
CourierUser = Annotated[User, Depends(check_role(UserRole.COURIER))]
PartnerOrConsumerUser = Annotated[
    User, Depends(check_role(UserRole.PARTNER, UserRole.CONSUMER))
]
AnyUser = CurrentUser
