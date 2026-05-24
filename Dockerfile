FROM public.ecr.aws/lambda/python:3.12

# Install deps

COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /bin/

# copy lock and pyproject
WORKDIR /app
COPY pyproject.toml uv.lock ./

# install deps with uv
RUN uv sync --frozen --no-dev

RUN cp -r /app/.venv/lib/python3.12/site-packages/* ${LAMBDA_TASK_ROOT}/

WORKDIR ${LAMBDA_TASK_ROOT}

# Copy function code
COPY ./src/* ${LAMBDA_TASK_ROOT}

# set the entry point to handler
CMD ["ingestor.lambda_handler"]

