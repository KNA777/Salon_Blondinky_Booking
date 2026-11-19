from fastapi import APIRouter

from app.api.appointments import router as appointments_router
from app.api.clients import router as clients_router
from app.api.masters import router as master_router
from app.api.services import router as service_router
from app.api.slots import router as slots_router
from app.api.working_hours import router as working_hours_router

main_router = APIRouter()

main_router.include_router(service_router)
main_router.include_router(master_router)
main_router.include_router(working_hours_router)
main_router.include_router(slots_router)
main_router.include_router(clients_router)
main_router.include_router(appointments_router)
