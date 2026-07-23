@echo off
set OTEL_RESOURCE_ATTRIBUTES=service.name=mock-workday-orchestrate
set OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
set OTEL_EXPORTER_OTLP_PROTOCOL=grpc
set OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true
set OTEL_LOGS_EXPORTER=otlp
opentelemetry-instrument python workday_ui.py
