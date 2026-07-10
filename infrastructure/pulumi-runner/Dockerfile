FROM python:3.12-slim

# Install Pulumi CLI
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \
    curl -fsSL https://get.pulumi.com | sh && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.pulumi/bin:${PATH}"

# Install Pulumi Python SDKs
RUN pip install --no-cache-dir \
    pulumi>=3.0 \
    pulumi-aws>=6.0

WORKDIR /app

# Default: run pulumi preview; overridden by the runner at task time
ENTRYPOINT ["pulumi"]
CMD ["version"]
