from fastapi import Depends

from app.core.security import get_current_user, get_optional_user


CurrentUser = Depends(get_current_user)
OptionalUser = Depends(get_optional_user)

