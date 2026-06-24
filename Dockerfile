FROM python:3-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip3 install --upgrade pip && pip install -r requirements.txt

COPY app.py ./

EXPOSE 7166

CMD ["gunicorn", "app:app", "-b", "0.0.0.0:7166", "-w", "4"]
