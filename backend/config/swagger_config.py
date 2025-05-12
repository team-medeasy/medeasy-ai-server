# backend/config/swagger_config.py
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def setup_swagger(app: FastAPI, title: str, version: str, description: str):
    """
    Swagger UI 및 OpenAPI 설정을 구성합니다.
    """

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema

        openapi_schema = get_openapi(
            title=title,
            version=version,
            description=description,
            routes=app.routes,
        )

        # components 객체가 없으면 생성
        if "components" not in openapi_schema:
            openapi_schema["components"] = {}

        # schemas 객체가 없으면 생성
        if "schemas" not in openapi_schema["components"]:
            openapi_schema["components"]["schemas"] = {}

        # 보안 스키마 추가
        openapi_schema["components"]["securitySchemes"] = {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "JWT 토큰을 입력하세요. 예: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            }
        }

        # 모든 경로에 보안 요구사항 추가
        openapi_schema["security"] = [{"bearerAuth": []}]

        app.openapi_schema = openapi_schema
        return app.openapi_schema

    # 커스텀 OpenAPI 스키마 설정
    app.openapi = custom_openapi

    return app  # 반드시 app을 반환해야 합니다