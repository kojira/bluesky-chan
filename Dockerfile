FROM python:3.10-slim

RUN mkdir /var/bot
WORKDIR /var/bot
ADD . /var/bot

RUN apt-get update \
  && apt-get install -y locales locales-all

ENV LANG="ja_JP.UTF-8" \
  LANGUAGE="ja_JP:ja" \
  LC_ALL="ja_JP.UTF-8"

RUN apt-get install libpangocairo-1.0-0

RUN pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install -r requirements.txt