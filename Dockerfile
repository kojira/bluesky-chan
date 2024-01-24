FROM python:3.12-slim

RUN mkdir /var/bot
WORKDIR /var/bot
ADD . /var/bot

RUN apt-get update \
  && apt-get install -y locales locales-all

ENV LANG="ja_JP.UTF-8" \
  LANGUAGE="ja_JP:ja" \
  LC_ALL="ja_JP.UTF-8"

RUN apt-get install -y libpangocairo-1.0-0 curl gcc libffi-dev

ENV RUST_HOME /usr/local/lib/rust
ENV RUSTUP_HOME ${RUST_HOME}/rustup
ENV CARGO_HOME ${RUST_HOME}/cargo
RUN mkdir /usr/local/lib/rust && \
    chmod 0755 $RUST_HOME
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs > ${RUST_HOME}/rustup.sh \
    && chmod +x ${RUST_HOME}/rustup.sh \
    && ${RUST_HOME}/rustup.sh -y --default-toolchain nightly --no-modify-path
ENV PATH $PATH:$CARGO_HOME/bin

RUN apt-get install -y zlib1g-dev libjpeg-dev

RUN pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install -r requirements.txt

RUN apt-get install -y git g++

RUN mkdir /var/work
WORKDIR /var/work
RUN git clone -b 0.60.0dev0 https://github.com/numba/numba.git
WORKDIR /var/work/numba
RUN pip install -e .