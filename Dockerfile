FROM python:3.11-slim

RUN useradd -m -u 1000 user
RUN mkdir -p /app && chown user:user /app

USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app
COPY --chown=user . /app

RUN pip install --no-cache-dir uv && uv sync

EXPOSE 7860
CMD ["uv", "run", "python", "visualization.py", "./aiq-evaluations", "--server"]
