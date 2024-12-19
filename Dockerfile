FROM python:3-slim

WORKDIR /app

COPY app.py requirements.txt .

RUN pip3 install --upgrade pip && pip install -r requirements.txt

EXPOSE 7166

CMD ["gunicorn", "app:app", "-b", "0.0.0.0:7166", "-w", "4"]
