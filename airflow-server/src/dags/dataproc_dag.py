from airflow import DAG
from airflow.providers.google.cloud.operators.dataproc import (
    DataprocCreateClusterOperator,
    DataprocDeleteClusterOperator,
    DataprocSubmitJobOperator,
    ClusterGenerator,
)
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from dotenv import load_dotenv
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pySpark.fetch_apis.fetch_disease_data import fetch_disease_death
from pySpark.fetch_apis.fetch_infrastructure_data import fetch_infrastucture_data
from pySpark.fetch_apis.fetch_our_world_data import fetch_our_world_data



load_dotenv()

# constants
SUB_URI = os.getenv("SUB_URI")
SERVICE_ACCOUNT = os.getenv("SERVICE_ACCOUNT")
PROJECT_ID = os.getenv("PROJECT_ID")
BUCKET_NAME = os.getenv("BUCKET_NAME")
CLUSTER_NAME = "travel-spark-cluster"
REGION = "us-central1"

CLUSTER_CONFIG = ClusterGenerator(
    project_id=PROJECT_ID,
    zone="us-central1-a",
    master_machine_type="n1-standard-2",
    worker_machine_type="n1-standard-2",
    num_workers=2,
    worker_disk_size=30,
    master_disk_size=30,
    storage_bucket=BUCKET_NAME,
    gce_cluster_config={
        "subnetwork_uri": SUB_URI,       
        "internal_ip_only": True,
        "service_account": SERVICE_ACCOUNT,
    },
    initialization_actions=[
        {"executable_file": f"gs://{BUCKET_NAME}/scripts/dependencies/install_dependencies.sh"} # install dotenv
    ],
).make()

DISEASE_FETCH = {
    "reference": {"project_id": PROJECT_ID},
    "placement": {"cluster_name": CLUSTER_NAME},
    "pyspark_job": {
        "main_python_file_uri": f"gs://{BUCKET_NAME}/scripts/jobs/fetch_apis/fetch_disease_data.py",
        "python_file_uris": [
            f"gs://{BUCKET_NAME}/scripts/dependencies/bucket_to_spark.env"
        ], 
    },
}

INFRASTRUCTURE_FETCH = {
    "reference": {"project_id": PROJECT_ID},
    "placement": {"cluster_name": CLUSTER_NAME},
    "pyspark_job": {
        "main_python_file_uri": f"gs://{BUCKET_NAME}/scripts/jobs/fetch_apis/fetch_infrastructure_data.py",
        "python_file_uris": [
            f"gs://{BUCKET_NAME}/scripts/dependencies/bucket_to_spark.env"
        ], 
    },
}

OUR_WORLD_FETCH = {
    "reference": {"project_id": PROJECT_ID},
    "placement": {"cluster_name": CLUSTER_NAME},
    "pyspark_job": {
        "main_python_file_uri": f"gs://{BUCKET_NAME}/scripts/jobs/fetch_apis/fetch_our_world_data.py",
        "python_file_uris": [
            f"gs://{BUCKET_NAME}/scripts/dependencies/bucket_to_spark.env"
        ], 
    },
}

PYSPARK_CLEAN = {
    "reference": {"project_id": PROJECT_ID},
    "placement": {"cluster_name": CLUSTER_NAME},
    "pyspark_job": {
        "main_python_file_uri": f"gs://{BUCKET_NAME}/scripts/jobs/clean_tables.py",
        "python_file_uris": [
            f"gs://{BUCKET_NAME}/scripts/dependencies/bucket_to_spark.env"
        ], 
    },
}

PYSPARK_AGG = {
    "reference": {"project_id": PROJECT_ID},
    "placement": {"cluster_name": CLUSTER_NAME},
    "pyspark_job": {
        "main_python_file_uri": f"gs://{BUCKET_NAME}/scripts/jobs/aggregate_tables.py",
        "python_file_uris": [
            f"gs://{BUCKET_NAME}/scripts/dependencies/bucket_to_spark.env"
        ], 
    },
}

PYSPARK_MERGE = {
    "reference": {"project_id": PROJECT_ID},
    "placement": {"cluster_name": CLUSTER_NAME},
    "pyspark_job": {
        "main_python_file_uri": f"gs://{BUCKET_NAME}/scripts/jobs/merge_tables.py",
        "python_file_uris": [
            f"gs://{BUCKET_NAME}/scripts/dependencies/bucket_to_spark.env"
        ], 
    },
}

PYSPARK_WRITE_BIGQUERY = {
    "reference": {"project_id": PROJECT_ID},
    "placement": {"cluster_name": CLUSTER_NAME},
    "pyspark_job": {
        "main_python_file_uri": f"gs://{BUCKET_NAME}/scripts/jobs/to_bigquery.py",
        "python_file_uris": [
            f"gs://{BUCKET_NAME}/scripts/dependencies/bucket_to_spark.env"
        ], 
    },
}

default_args = {
    'start_date': days_ago(1),
    'retries': 1,
}

# DAG definition
with DAG(
    'dataproc_etl_pipeline',
    default_args=default_args,
    schedule_interval=None,
    catchup=False,
) as dag:

    fetch_our_world_job = PythonOperator(
        task_id='fetch_our_world_job',
        python_callable=fetch_our_world_data,
    )
    fetch_disease_job = PythonOperator(
        task_id='fetch_disease_job',
        python_callable=fetch_disease_death,
    )
    fetch_infrastructure_job = PythonOperator(
        task_id='fetch_infrastructure_job',
        python_callable=fetch_infrastucture_data,
    )

    # create Dataproc cluster
    create_cluster = DataprocCreateClusterOperator(
        task_id="create_cluster",
        project_id=PROJECT_ID,
        region=REGION,
        cluster_name=CLUSTER_NAME,
        cluster_config=CLUSTER_CONFIG,
    )


    # submit Spark job
    spark_job_clean = DataprocSubmitJobOperator(
        task_id="spark_job_clean",
        job=PYSPARK_CLEAN,
        region=REGION,
        project_id=PROJECT_ID,
    )

    spark_job_agg = DataprocSubmitJobOperator(
        task_id="spark_job_agg",
        job=PYSPARK_AGG,
        region=REGION,
        project_id=PROJECT_ID,
    )

    spark_job_merge = DataprocSubmitJobOperator(
        task_id="spark_job_merge",
        job=PYSPARK_MERGE,
        region=REGION,
        project_id=PROJECT_ID,
    )

    spark_job_write_bigquery = DataprocSubmitJobOperator(
        task_id="spark_job_write_bigquery",
        job=PYSPARK_WRITE_BIGQUERY,
        region=REGION,
        project_id=PROJECT_ID,
    )

    # delete Dataproc cluster
    delete_cluster = DataprocDeleteClusterOperator(
        task_id="delete_cluster",
        project_id=PROJECT_ID,
        region=REGION,
        cluster_name=CLUSTER_NAME,
        trigger_rule="all_done",  # ensures cluster deletion runs even if tasks fail
    )

    # task dependencies
    [fetch_disease_job, fetch_infrastructure_job, fetch_our_world_job] >>\
    create_cluster >>\
    spark_job_clean >> spark_job_agg >> spark_job_merge >> spark_job_write_bigquery >>\
    delete_cluster
