FROM mcr.microsoft.com/azurelinux/base/python:3.12

USER root

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/IBG

WORKDIR /app

COPY requirements-runtime.txt ./
RUN tdnf install -y iproute iproute-tc \
    && tdnf clean all
RUN python3 -m pip install --no-cache-dir -r requirements-runtime.txt "scipy==1.18.0"

COPY IBG ./IBG
COPY MILP ./MILP
COPY testbed ./testbed

USER 10001:10001

EXPOSE 8080 8081

CMD ["python3", "-m", "uvicorn", "MILP.kernel_flow_generator:app", "--host", "0.0.0.0", "--port", "8080"]
