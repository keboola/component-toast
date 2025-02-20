FROM python:3.13-slim

ENV PYTHONIOENCODING=utf-8

RUN pip3 install uv

COPY requirements.txt /code/requirements.txt
RUN uv pip sync --system /code/requirements.txt

COPY /src /code/src/
COPY /tests /code/tests/
COPY /scripts /code/scripts/
COPY flake8.cfg /code/flake8.cfg
COPY deploy.sh /code/deploy.sh

WORKDIR /code/

CMD ["python", "-u", "/code/src/component.py"]
