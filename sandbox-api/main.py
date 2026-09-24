import logging
import os

from fastapi import FastAPI

from api.routes import router
from application.sandbox_service import SandboxService
from infrastructure.k8s_gateway import K8sGateway

SERVICE_NAME = "sandbox-api"
NAMESPACE = os.getenv("SANDBOX_NAMESPACE", "default")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(SERVICE_NAME)

gateway = K8sGateway(NAMESPACE)
sandbox_service = SandboxService(gateway)

app = FastAPI(title=SERVICE_NAME)
app.state.sandbox_service = sandbox_service
app.include_router(router)
