FROM python:3.11.9-slim-bookworm
WORKDIR /app
COPY . .
RUN pip install .

EXPOSE 8050
ENV HOST=0.0.0.0
CMD [ "netmedex", "run" ]
