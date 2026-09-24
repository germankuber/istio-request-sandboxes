from fastapi import APIRouter, Depends, HTTPException, Request

from api.schemas import (
    ExternalHostResponse,
    RuleCreateRequest,
    RuleResponse,
    RuleUpdateRequest,
)
from application.rule_service import RuleConflictError, RuleNotFoundError, RuleService
from domain.rule import ExternalHost

router = APIRouter()


def get_rule_service(request: Request) -> RuleService:
    return request.app.state.rule_service


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "mock-manager"}


@router.get("/externals", response_model=list[ExternalHostResponse])
def list_externals() -> list[ExternalHostResponse]:
    return [ExternalHostResponse(id=host.value, label=host.value) for host in ExternalHost]


@router.get("/rules", response_model=list[RuleResponse])
def list_rules(
    sandbox_id: str | None = None, service: RuleService = Depends(get_rule_service)
) -> list[RuleResponse]:
    return [RuleResponse.from_domain(rule) for rule in service.list_rules(sandbox_id)]


RULE_CONFLICT_DETAIL = "a rule already exists for this sandbox_id, host, method, path"


@router.post("/rules", response_model=RuleResponse, status_code=201)
def create_rule(
    payload: RuleCreateRequest, service: RuleService = Depends(get_rule_service)
) -> RuleResponse:
    try:
        rule = service.create_rule(
            sandbox_id=payload.sandbox_id,
            host=payload.host,
            method=payload.method,
            path=payload.path,
            status=payload.status,
            headers=payload.headers,
            body=payload.body,
            delay_ms=payload.delay_ms,
            enabled=payload.enabled,
        )
    except RuleConflictError:
        raise HTTPException(status_code=409, detail=RULE_CONFLICT_DETAIL)
    return RuleResponse.from_domain(rule)


@router.get("/rules/{rule_id}", response_model=RuleResponse)
def get_rule(rule_id: str, service: RuleService = Depends(get_rule_service)) -> RuleResponse:
    try:
        return RuleResponse.from_domain(service.get_rule(rule_id))
    except RuleNotFoundError:
        raise HTTPException(status_code=404, detail="rule not found")


@router.put("/rules/{rule_id}", response_model=RuleResponse)
def update_rule(
    rule_id: str,
    payload: RuleUpdateRequest,
    service: RuleService = Depends(get_rule_service),
) -> RuleResponse:
    try:
        rule = service.update_rule(rule_id, **payload.model_dump(exclude_unset=True))
    except RuleNotFoundError:
        raise HTTPException(status_code=404, detail="rule not found")
    except RuleConflictError:
        raise HTTPException(status_code=409, detail=RULE_CONFLICT_DETAIL)
    return RuleResponse.from_domain(rule)


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: str, service: RuleService = Depends(get_rule_service)) -> None:
    try:
        service.delete_rule(rule_id)
    except RuleNotFoundError:
        raise HTTPException(status_code=404, detail="rule not found")


@router.post("/rules/{rule_id}/toggle", response_model=RuleResponse)
def toggle_rule(
    rule_id: str, service: RuleService = Depends(get_rule_service)
) -> RuleResponse:
    try:
        rule = service.toggle_rule(rule_id)
    except RuleNotFoundError:
        raise HTTPException(status_code=404, detail="rule not found")
    return RuleResponse.from_domain(rule)
