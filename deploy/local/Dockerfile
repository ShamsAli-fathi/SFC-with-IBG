FROM mcr.microsoft.com/azurelinux/base/python:3.12

USER root

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/IBG

WORKDIR /app

COPY requirements-runtime.txt ./
RUN python3 -m pip install --no-cache-dir -r requirements-runtime.txt

COPY IBG ./IBG
COPY testbed ./testbed

USER 10001:10001

EXPOSE 8080

CMD ["python3", "-m", "uvicorn", "testbed.cnf_service:app", "--host", "0.0.0.0", "--port", "8080"]
