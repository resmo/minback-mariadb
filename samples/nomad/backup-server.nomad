# Long-running variant: backups run on an internal schedule or via
# POST /backup, and /metrics can be scraped by Prometheus.
variable "datacenters" {
  type    = list(string)
  default = ["dc1"]
}
variable "project" {
  type    = string
  default = "default"
}
variable "env" {
  type    = string
  default = "prod"
}
variable "version" {
  type    = string
  default = "main"
}
variable "namespace" {
  type    = string
  default = ""
}
variable "schedule" {
  type    = string
  default = "0 3 * * *"
}

locals {
  namespace  = "${var.namespace != "" ? var.namespace : format("%s-%s", var.project, var.env)}"
  force_pull = substr(var.version, 0, 1) != "v"
}

job "mariadb-backup" {
  datacenters = var.datacenters
  namespace   = local.namespace
  type        = "service"

  meta {
    version = var.version
  }

  group "mariadb-backup" {
    count = 1

    network {
      port "http" {
        to = 8080
      }
    }

    service {
      name = "${local.namespace}-mariadb-backup"
      port = "http"
      tags = ["prometheus"]

      meta {
        metrics_path = "/metrics"
      }

      check {
        type     = "http"
        path     = "/healthz"
        interval = "30s"
        timeout  = "5s"
      }
    }

    task "mariadb-backup" {
      driver = "docker"

      config {
        image      = "ghcr.io/resmo/minback-mariadb:${var.version}"
        force_pull = local.force_pull
        args       = ["serve"]
        ports      = ["http"]
      }

      template {
        data        = <<EOH
DB="immo"
DB_USER="immo"
{{ range service "${local.namespace}-mariadb" }}
DB_HOST="{{ .Address }}"
DB_PORT="{{ .Port }}"
{{ end }}

OBJECT_SERVER="https://s3.example.com"
OBJECT_BUCKET="${local.namespace}-backups"

SCHEDULE="${var.schedule}"
NOTIFY_ON="failure"
EOH
        destination = "${NOMAD_TASK_DIR}/backup.env"
        env         = true
      }

      template {
        data        = <<EOH
DB_PASSWORD="..."
OBJECT_ACCESS_KEY=...
OBJECT_SECRET_KEY=...
API_TOKEN=...
NOTIFY_WEBHOOK_URL=...
EOH
        destination = "${NOMAD_SECRETS_DIR}/backup.env"
        env         = true
      }

      resources {
        cpu    = 100
        memory = 128
      }
    }
  }
}
