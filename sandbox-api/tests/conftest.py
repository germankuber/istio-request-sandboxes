from domain.errors import SandboxNotFoundError
from domain.sandbox import BaselineDeployment


class FakeSandboxPort:
    def __init__(
        self,
        sandboxes: dict[str, dict] | None = None,
        deployments: list[BaselineDeployment] | None = None,
    ) -> None:
        self._sandboxes: dict[str, dict] = dict(sandboxes or {})
        self._deployments = list(deployments or [])

    def list_sandboxes(self) -> list[dict]:
        return list(self._sandboxes.values())

    def get_sandbox(self, name: str) -> dict | None:
        return self._sandboxes.get(name)

    def create_sandbox(self, body: dict) -> dict:
        name = body["metadata"]["name"]
        created = {**body, "status": {"phase": "Pending", "message": ""}}
        self._sandboxes[name] = created
        return created

    def delete_sandbox(self, name: str) -> None:
        if name not in self._sandboxes:
            raise SandboxNotFoundError(name)
        del self._sandboxes[name]

    def list_baseline_deployments(self) -> list[BaselineDeployment]:
        return list(self._deployments)
