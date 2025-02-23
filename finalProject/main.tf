terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = "serverlessfinalproject"
  region  = "europe-west3"
}

# Storage buckets for different data stages
resource "google_storage_bucket" "raw_data" {
  name          = "serverlessfinalproject-raw-data-bucket"
  location      = "EUROPE-WEST3"
  force_destroy = true
}

resource "google_storage_bucket" "citation_graph" {
  name          = "serverlessfinalproject-citation-graph-bucket"
  location      = "EUROPE-WEST3"
  force_destroy = true
}

resource "google_storage_bucket" "results" {
  name          = "serverlessfinalproject-results-bucket"
  location      = "EUROPE-WEST3"
  force_destroy = true
}

# Bucket to store Cloud Function code
resource "google_storage_bucket" "function_bucket" {
  name          = "serverlessfinalproject-function-code-bucket"
  location      = "EUROPE-WEST3"
  force_destroy = true
}

# Cloud Function source code object for fetch_data
resource "google_storage_bucket_object" "fetch_data_code" {
  name   = "cloud_functions/fetch_data/fetch-data.zip"
  bucket = google_storage_bucket.function_bucket.name
  source = "cloud_functions/fetch_data/fetch-data.zip"
}

# Cloud Function source code object for preprocess_data
resource "google_storage_bucket_object" "preprocess_data_code" {
  name   = "cloud_functions/preprocess_data/preprocess-data.zip"
  bucket = google_storage_bucket.function_bucket.name
  source = "cloud_functions/preprocess_data/preprocess-data.zip"
}

# Cloud Function resource for fetch_data (triggered by object creation in raw_data bucket)
resource "google_cloudfunctions_function" "fetch_data" {
  name        = "fetch-data"
  runtime     = "python310"
  region      = "europe-west3"
  source_archive_bucket = google_storage_bucket.function_bucket.name
  source_archive_object = google_storage_bucket_object.fetch_data_code.name
  entry_point = "fetch_data"
  event_trigger {
    event_type = "google.storage.object.finalize"
    resource   = google_storage_bucket.raw_data.name
  }
  service_account_email = google_service_account.function_service_account.email
}

# Cloud Function resource for preprocess_data (triggered by object creation in raw_data bucket)
resource "google_cloudfunctions_function" "preprocess_data" {
  name        = "preprocess-data"
  runtime     = "python310"
  region      = "europe-west3"
  source_archive_bucket = google_storage_bucket.function_bucket.name
  source_archive_object = google_storage_bucket_object.preprocess_data_code.name
  entry_point = "fetch_and_process_works_data" 
  event_trigger {
    event_type = "google.storage.object.finalize"
    resource   = google_storage_bucket.raw_data.name
  }
  service_account_email = google_service_account.function_service_account.email
}

# Workflow resource
resource "google_workflows_workflow" "research_workflow" {
  name            = "research-analysis-workflow"
  region          = "europe-west3"
  source_contents = file("${path.module}/workflow.yaml")
}

# Service account for the Cloud Function
resource "google_service_account" "function_service_account" {
  account_id   = "function-service-account"
  display_name = "Cloud Function Service Account"
}

# Grant the service account permission to read from Cloud Storage
resource "google_storage_bucket_iam_member" "function_storage_permission" {
  bucket = google_storage_bucket.raw_data.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.function_service_account.email}"
}

# Grant the service account permission to invoke Cloud Functions
resource "google_project_iam_member" "function_invoker" {
  project = "serverlessfinalproject"
  role    = "roles/cloudfunctions.invoker"
  member  = "serviceAccount:${google_service_account.function_service_account.email}"
}

# Grant the service account permission to write to the citation graph bucket
resource "google_storage_bucket_iam_member" "function_citation_graph_permission" {
  bucket = google_storage_bucket.citation_graph.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.function_service_account.email}"
}

# Grant the service account permission to write to the results bucket
resource "google_storage_bucket_iam_member" "function_results_permission" {
  bucket = google_storage_bucket.results.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.function_service_account.email}"
}
