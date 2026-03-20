FROM python:3.11-slim

WORKDIR /app

RUN pip install flask

COPY app.py .
COPY inject.py .

CMD ["python", "app.py"]
