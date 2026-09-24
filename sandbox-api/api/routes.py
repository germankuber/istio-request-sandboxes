from fastapi import APIRouter, Depends, HTTPException, Request

from api.schemas import (
    SandboxCreateRequest,
    SandboxDetailResponse,
    SandboxSummaryResponse,
    ServiceInfoResponse,
)
from application.sandbox_service import SandboxService
from domain.errors import SandboxAlreadyExistsError, SandboxNotFoundError

router = APIRouter()


def get_sandbox_service(request: Request) -> SandboxService:
    return request.app.state.sandbox_service


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "sandbox-api"}


@router.get("/services", response_model=list[ServiceInfoResponse])
def list_services(
    service: SandboxService = Depends(get_sandbox_service),
) -> list[ServiceInfoResponse]:
    return [ServiceInfoResponse.from_domain(info) for info in service.list_services()]


@router.get("/sandboxes", response_model=list[SandboxSummaryResponse])
def list_sandboxes(
    service: SandboxService = Depends(get_sandbox_service),
) -> list[SandboxSummaryResponse]:
    return [
        SandboxSummaryResponse(
            name=item.name,
            phase=item.phase,
            message=item.message,
            services=list(item.service_names),
            mocks_count=item.mocks_count,
            created_at=item.created_at,
        )
        for item in service.list_sandboxes()
    ]


@router.get("/sandboxes/{name}", response_model=SandboxDetailResponse)
def get_sandbox(
    name: str, service: SandboxService = Depends(get_sandbox_service)
) -> SandboxDetailResponse:
    try:
        sandbox = service.get_sandbox(name)
    except SandboxNotFoundError:
        raise HTTPException(status_code=404, detail="sandbox not found")
    return _to_detail_response(sandbox, name)


@router.post("/sandboxes", response_model=SandboxDetailResponse, status_code=201)
def create_sandbox(
    payload: SandboxCreateRequest, service: SandboxService = Depends(get_sandbox_service)
) -> SandboxDetailResponse:
    try:
        created = service.create_sandbox(
            name=payload.name,
            services=tuple(item.to_domain() for item in payload.services),
            mocks=tuple(item.to_domain() for item in payload.mocks),
        )
    except SandboxAlreadyExistsError:
        raise HTTPException(status_code=409, detail=f"sandbox '{payload.name}' already exists")
    return _to_detail_response(created, payload.name)


@router.delete("/sandboxes/{name}", status_code=204)
def delete_sandbox(name: str, service: SandboxService = Depends(get_sandbox_service)) -> None:
    try:
        service.delete_sandbox(name)
    except SandboxNotFoundError:
        raise HTTPException(status_code=404, detail="sandbox not found")


def _to_detail_response(sandbox: dict, fallback_name: str) -> SandboxDetailResponse:
    return SandboxDetailResponse(
        name=sandbox.get("metadata", {}).get("name", fallback_name),
        spec=sandbox.get("spec", {}),
        status=sandbox.get("status", {}),
    )
