"""`/health` için gerçek HTTP entegrasyon testi.

Gerçek dev Postgres + Qdrant'a karşı çalışır (`tests/integration/conftest.py`
`api_client` fixture'ı) — hiçbir sahte sağlayıcı/DB override'ı yok, bu
endpoint zaten kendi başına "derin health-check" (bkz. backend/api/routes.py).
"""

import httpx
import pytest

from backend.api.schemas import HealthCheckResponse

pytestmark = pytest.mark.integration


async def test_health_returns_200_and_healthy_when_dependencies_are_up(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/health")

    assert response.status_code == 200
    body = HealthCheckResponse.model_validate(response.json())
    assert body.status == "healthy"
    dependency_names = {dep.name for dep in body.dependencies}
    assert dependency_names == {"postgres", "qdrant", "llm_config"}
    assert all(dep.healthy for dep in body.dependencies)
