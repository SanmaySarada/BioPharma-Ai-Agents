FROM rocker/r-ver:4.5.2

LABEL org.omni-agents.component="r-executor"

# Install system dependencies required by R packages
RUN echo 'Acquire::http::Pipeline-Depth "0";' > /etc/apt/apt.conf.d/99fixhash && \
    echo 'Acquire::http::No-Cache=True;' >> /etc/apt/apt.conf.d/99fixhash && \
    echo 'Acquire::BrokenProxy=true;' >> /etc/apt/apt.conf.d/99fixhash && \
    echo 'Acquire::Retries "3";' >> /etc/apt/apt.conf.d/99fixhash && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean && \
    apt-get update && \
    apt-get install -y \
    libcurl4-openssl-dev \
    libssl-dev \
    libxml2-dev \
    libfontconfig1-dev \
    libfreetype6-dev \
    libpng-dev \
    libtiff5-dev \
    libjpeg-dev \
    && rm -rf /var/lib/apt/lists/*

# Use Posit Package Manager for pre-compiled Linux binaries (avoids 30-min source compilation)
RUN R -e "options(repos = c(CRAN = 'https://packagemanager.posit.co/cran/__linux__/noble/latest')); \
    install.packages(c('survival', 'survminer', 'tidyverse', 'haven', 'jsonlite', 'readr', 'ggplot2', 'broom'))"

# Copy healthcheck script to verify all packages load
COPY healthcheck.R /opt/healthcheck.R

WORKDIR /workspace

CMD ["Rscript"]
