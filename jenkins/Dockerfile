FROM jenkins-lab:lts

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /usr/share/jenkins/ref/jobs/visitor-counter-pipeline

COPY job-config.xml /usr/share/jenkins/ref/jobs/visitor-counter-pipeline/config.xml
