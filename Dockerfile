FROM python:3.12-alpine

# Create a non-root user
RUN adduser -D -u 1000 appuser

# copy the requirements file into the image
COPY ./requirements.txt /app/requirements.txt

# switch working directory
WORKDIR /app

# Install system dependencies
RUN apk add --no-cache --virtual --update \
    python3-dev gcc \
    gfortran musl-dev g++ \
    libffi-dev openssl-dev \
    libxml2 libxml2-dev \
    libxslt libxslt-dev \
    libjpeg-turbo-dev zlib-dev \
    libpq postgresql-dev \
    musl-dev wget git build-base \
    cairo-dev freetype-dev harfbuzz-dev fribidi-dev \
    pango-dev gdk-pixbuf-dev shared-mime-info \
    fontconfig ttf-freefont ttf-dejavu ttf-droid ttf-liberation

# install the dependencies and packages in the requirements file
RUN pip install --upgrade pip \ 
    && pip install -r requirements.txt

# copy every content from the local file to the image
COPY . /app

# Change ownership of the /app directory to appuser
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# configure the container to run in an executed manner
ENTRYPOINT [ "python" ]

CMD ["main.py"]