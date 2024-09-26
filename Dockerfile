FROM python:3.11.9-slim-bookworm
WORKDIR /app
COPY . .
RUN pip install .[dash]

EXPOSE 8050
CMD [ "python3", "pubtoscape_app/app.py" ]
