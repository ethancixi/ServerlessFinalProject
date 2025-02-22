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

# Cloud Function source code object
resource "google_storage_bucket_object" "fetch_data_code" {
  name   = "cloud_functions/fetch_data/fetch-data.zip"
  bucket = google_storage_bucket.function_bucket.name
  source = "cloud_functions/fetch_data/fetch-data.zip"
}

# Cloud Function resource
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
