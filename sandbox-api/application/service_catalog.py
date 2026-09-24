from domain.sandbox import BaselineDeployment, ServiceInfo

INFRA_EXACT_NAMES = {"frontend", "postgres"}
INFRA_NAME_PREFIXES = ("mock-", "sandbox-")


def is_sandboxable_app(app: str) -> bool:
    if not app:
        return False
    if app in INFRA_EXACT_NAMES:
        return False
    return not app.startswith(INFRA_NAME_PREFIXES)


def sandboxable_services(deployments: list[BaselineDeployment]) -> list[ServiceInfo]:
    services = [
        ServiceInfo(name=deployment.app, uses_db="DATABASE_URL" in deployment.env)
        for deployment in deployments
        if deployment.version == "baseline" and is_sandboxable_app(deployment.app)
    ]
    return sorted(services, key=lambda service: service.name)
