from datetime import datetime,timedelta
import uuid
from airflow import DAG
from airflow.providers.google.cloud.operators.dataproc import DataprocCreateBatchOperator
from airflow.providers.google.cloud.sensors.gcs import GCSObjectExistenceSensor
from airflow.models import Variable

# DAG default arguments
default_args = {
    'owner':'airflow',
    'depends_on_past': False,
    'retries':1,
    'retry_delay':timedelta(minutes=5),
    'start_date':datetime(2025,3,13)
}

# Define the DAG
with DAG(
    dag_id="flight_booking_dataproc_bq_dag",
    default_args=default_args,
    schedule_interval=None,
    catchup=False,
) as dag:
    # Fetch environment variables
    env = Variable.get("env",default_var="dev")
    gcs_bucket = Variable.get("gcs_bucket",default_var="airflow-projetcs-gds")
    bq_project = Variable.get("bq_project",default_var="amiable-vent-454406-h2")
    bq_dataset = Variable.get("bq_dataset",default_var=f"flight_data_{env}")
    tables = Variable.get("tables",deserialize_json=True)
    
    # Extract table names from the 'tables' variable
    transformed_table = tables['transformed_table']
    route_insights_table = tables['route_insights_table']
    origin_insights_table = tables['origin_insights_table']
    
    # Generate a unique batch ID using UUID
    
    batch_id = f"flight-booking-batch-{env}-{str(uuid.uuid4())[:8]}"
    
    # Task 1: File Sensor for GCS
    
    file_sensor = GCSObjectExistenceSensor(
        task_id="check_file_arrival",
        bucket=gcs_bucket,
        object=f"airflow-project-1/source-{env}/flight_booking.csv",
        google_cloud_conn_id="google_cloud_default",
        timeout=300,
        poke_interval = 30,
        mode="poke"
    )
    
    # Task 2: Submit PySpark job to Dataproc Serverless
    
    batch_details = {
        "pyspark_batch":{
            "main_python_file_uri":f"gs://{gcs_bucket}/airflow-project-1/spark-job/spark_transformation_job.py",
            "python_file_uris":[],
            "jar_file_uris":[],
            "args":[
                f"--env={env}",
                f"--bq_project={bq_project}",
                f"--bq_dataset={bq_dataset}",
                f"--transformed_table={transformed_table}",
                f"--route_insights_table={route_insights_table}",
                f"--origin_insights_table={origin_insights_table}",
            ]
        },
        "runtime_config": {
            "version":"2.2"
        },
        "environment_config":{
            "execution_config":{
                "service_account":"814467953394-compute@developer.gserviceaccount.com",
                "network_uri":"",
                "subnetwork_uri":""
            }
        }
    }
    
    pyspark_task = DataprocCreateBatchOperator(
        task_id="run_spark_job_on_dataproc_serverless",
        batch=batch_details,
        batch_id=batch_id,
        project_id="amiable-vent-454406-h2",
        region="us-central1",
        gcp_conn_id="google_cloud_default",
    )
    
    # Task Dependencies
    file_sensor >> pyspark_task
