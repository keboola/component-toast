FROM python:3.13-slim

ENV PYTHONIOENCODING utf-8

RUN apt-get update && apt-get install -y build-essential
RUN pip install uv flake8

COPY requirements.txt /code/requirements.txt
RUN uv venv
RUN uv pip sync /code/requirements.txt

COPY /src /code/src/
COPY /tests /code/tests/
COPY /scripts /code/scripts/
COPY flake8.cfg /code/flake8.cfg
COPY deploy.sh /code/deploy.sh

WORKDIR /code/

CMD ["python", "-u", "/code/src/component.py"]
