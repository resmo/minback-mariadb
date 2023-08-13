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
variable "cron" {
  type    = string
  default = "* */15 * * * * *"
}

locals {
  namespace  = "${var.namespace != "" ? var.namespace : format("%s-%s", var.project, var.env)}"
  force_pull = substr(var.version, 0, 1) != "v"
}

job "mariadb-backup" {
  datacenters = var.datacenters
  namespace   = local.namespace
  type        = "batch"

  periodic {
    cron             = var.cron
    prohibit_overlap = true
  }

  meta {
    version = var.version
  }

  group "mariadb-backup" {
    count = 1

    task "mariadb-backup" {
      driver = "docker"

      config {
        image      = "ghcr.io/resmo/minback-mariadb:${var.version}"
        force_pull = local.force_pull
      }

      template {
        data        = <<EOH
DB="immo"
DB_USER="immo"
{{ range service "${local.namespace}-mariadb" }}
DB_HOST="{{ .Address }}"
DB_PORT="{{ .Port }}"
{{ end }}

MINIO_SERVER="https://minio.example.com"
MINIO_BUCKET="${local.namespace}-backups"
EOH
        destination = "${NOMAD_TASK_DIR}/backup.env"
        env         = true
      }

      template {
        data        = <<EOH
DB_PASSWORD="..."
MINIO_ACCESS_KEY=...
MINIO_SECRET_KEY=...
EOH
        destination = "${NOMAD_SECRETS_DIR}/backup.env"
        env         = true
      }

      resources {
        cpu    = 100
        memory = 64
      }

    }
  }
}
