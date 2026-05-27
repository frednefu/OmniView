"""版本信息 API。"""
from fastapi import APIRouter
from app.version import get_version

router = APIRouter(tags=["版本"])


@router.get("/version")
def api_version():
    return {"version": get_version()}
