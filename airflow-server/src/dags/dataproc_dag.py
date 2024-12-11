from airflow import DAG
from airflow.providers.google.cloud.operators.dataproc import (
    DataprocCreateClusterOperator,
    DataprocDeleteClusterOperator,
    DataprocSubmitJobOperator,
    ClusterGenerator
)
from airflow.utils.dates import days_ago
from dotenv import load_dotenv
import os
load_dotenv()

# constants
PROJECT_ID = "test_travel_pipeline"
BUCKET_NAME = os.getenv("BUCKET_NAME")
CLUSTER_NAME = "spark_travel_cluster"
REGION = "us-central1"

CLUSTER_CONFIG = ClusterGenerator(
    project_id=PROJECT_ID,
    zone="us-central1-a",
    master_machine_type="n1-standard-2",
    worker_machine_type="n1-standard-2",
    num_workers=2,
    worker_disk_size=10,
    master_disk_size=20,
    storage_bucket=BUCKET_NAME,
).make()

PYSPARK_JOB = {
    "reference": {"project_id": PROJECT_ID},
    "placement": {"cluster_name": CLUSTER_NAME},
    "pyspark_job": {
        "main_python_file_uri": f"gs://{BUCKET_NAME}/scripts/jobs/bucket_to_spark.py",
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
    'dataproc_spark_job',
    default_args=default_args,
    schedule_interval=None,
    catchup=False,
) as dag:

    # create Dataproc cluster
    create_cluster = DataprocCreateClusterOperator(
        task_id="create_cluster",
        project_id=PROJECT_ID,
        region=REGION,
        cluster_name=CLUSTER_NAME,
        cluster_config=CLUSTER_CONFIG,
    )

    # submit Spark job
    submit_spark_job = DataprocSubmitJobOperator(
        task_id="submit_spark_job",
        job=PYSPARK_JOB,
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
    create_cluster >> submit_spark_job >> delete_cluster