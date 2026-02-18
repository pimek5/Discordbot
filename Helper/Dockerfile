FROM python:3.12-slim

WORKDIR /app

COPY Helper/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "Helper/main.py"]
