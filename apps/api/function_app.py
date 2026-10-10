"""Punto de entrada de Azure Functions (modelo de programación Python v2)."""

import azure.functions as func

from exam_engine.http.health import bp as health_bp

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
app.register_functions(health_bp)
