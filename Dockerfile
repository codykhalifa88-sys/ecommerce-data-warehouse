FROM apache/airflow:2.9.1-python3.11

USER root
COPY requirements.txt /requirements.txt

USER airflow
# Install against Airflow's own constraints file so pip can't resolve an
# incompatible SQLAlchemy (or other transitive dependency) version.
RUN pip install --no-cache-dir -r /requirements.txt \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.9.1/constraints-3.11.txt"

WORKDIR /opt/airflow
COPY etl /opt/airflow/etl
COPY sql /opt/airflow/sql
COPY dags /opt/airflow/dags
COPY tests /opt/airflow/tests
COPY dashboard /opt/airflow/dashboard

ENV AIRFLOW_PROJECT_ROOT=/opt/airflow
ENV PYTHONPATH=/opt/airflow
