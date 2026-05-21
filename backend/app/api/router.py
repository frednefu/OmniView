from fastapi import APIRouter
from app.api import auth, switches, results, scan_logs

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(switches.router)
api_router.include_router(results.router)
api_router.include_router(scan_logs.router)
