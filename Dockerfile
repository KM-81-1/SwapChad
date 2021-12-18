FROM python:3

# Copy app sources
WORKDIR /app
COPY . .

# Install requirements
RUN pip install -r requirements.txt

# Pull waiting script
ADD https://github.com/ufoscout/docker-compose-wait/releases/download/2.9.0/wait /wait
RUN chmod +x /wait

# Workaround for issue with locales
RUN apt-get update
RUN apt-get install -y locales
RUN sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen
RUN locale-gen

# Wait for db to become available ad start application
CMD /wait && python main.py
