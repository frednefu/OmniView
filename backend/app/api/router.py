from fastapi import APIRouter
from app.api import auth, switches, results, scan_logs, dashboard, subnets, search, history, users, vcenters

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(vcenters.router)
api_router.include_router(switches.router)
api_router.include_router(results.router)
api_router.include_router(scan_logs.router)
api_router.include_router(dashboard.router)
api_router.include_router(subnets.router)
api_router.include_router(search.router)
api_router.include_router(history.router)
