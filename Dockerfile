FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
     && apt-get install -y --no-install-recommends \
         build-essential \
         gcc \
         libffi-dev \
         libssl-dev \
         libjpeg-dev \
         zlib1g-dev \
         libsdl2-dev \
         libfreetype6-dev \
         libpng-dev \
         tk-dev \
          xvfb \
          xauth \
         libasound2 \
         pulseaudio \
     && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

EXPOSE 8080

CMD ["xvfb-run", "-s", "-screen 0 1024x768x24", "python", "1212.py"]
