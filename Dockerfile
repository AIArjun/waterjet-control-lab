FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8787
WORKDIR /app
COPY requirements-web.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements-web.txt
COPY src ./src
RUN pip install --no-cache-dir --no-deps . && useradd --create-home lab
USER lab
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8787')+'/healthz',timeout=2)"
CMD ["waterjet-lab"]
