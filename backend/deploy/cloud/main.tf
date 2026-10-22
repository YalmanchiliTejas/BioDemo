terraform {
  required_version = ">= 1.6.0"
  required_providers {
    digitalocean = { source = "digitalocean/digitalocean", version = "~> 2.0" }
  }
}
# DIGITALOCEAN_TOKEN is read from the environment, never put it in tfvars.
provider "digitalocean" {}

variable "name" { type = string }
variable "region" { type = string }
variable "ssh_key_ids" { type = list(string) }
variable "admin_cidrs" {
  type = list(string)
  validation {
    condition     = length(var.admin_cidrs) > 0 && !contains(var.admin_cidrs, "0.0.0.0/0") && !contains(var.admin_cidrs, "::/0")
    error_message = "SSH requires restricted administrator CIDRs."
  }
}
variable "size" {
  type    = string
  default = "s-4vcpu-8gb"
}
variable "data_volume_gib" {
  type    = number
  default = 100
}

resource "digitalocean_vpc" "main" {
  name   = var.name
  region = var.region
}
resource "digitalocean_droplet" "main" {
  name       = var.name
  region     = var.region
  size       = var.size
  image      = "ubuntu-24-04-x64"
  ssh_keys   = var.ssh_key_ids
  vpc_uuid   = digitalocean_vpc.main.id
  monitoring = true
  backups    = true
  user_data  = file("${path.module}/cloud-init.yml")
  lifecycle { prevent_destroy = true }
}
resource "digitalocean_volume" "data" {
  name        = "${var.name}-data"
  region      = var.region
  size        = var.data_volume_gib
  description = "Initialize with LUKS before placing application or Docker data here"
  lifecycle { prevent_destroy = true }
}
resource "digitalocean_volume_attachment" "data" {
  droplet_id = digitalocean_droplet.main.id
  volume_id  = digitalocean_volume.data.id
}
resource "digitalocean_firewall" "main" {
  name        = var.name
  droplet_ids = [digitalocean_droplet.main.id]
  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = var.admin_cidrs
  }
  inbound_rule {
    protocol         = "tcp"
    port_range       = "80"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }
  inbound_rule {
    protocol         = "tcp"
    port_range       = "443"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }
  outbound_rule {
    protocol              = "tcp"
    port_range            = "80"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
  outbound_rule {
    protocol              = "tcp"
    port_range            = "443"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
  outbound_rule {
    protocol              = "udp"
    port_range            = "53"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
  outbound_rule {
    protocol              = "tcp"
    port_range            = "53"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
  outbound_rule {
    protocol              = "udp"
    port_range            = "123"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}
resource "digitalocean_monitor_alert" "memory" {
  alerts { email = [var.operations_email] }
  window      = "5m"
  type        = "v1/insights/droplet/memory_utilization_percent"
  compare     = "GreaterThan"
  value       = 85
  enabled     = true
  entities    = [digitalocean_droplet.main.id]
  description = "${var.name}: memory pressure"
}
variable "operations_email" { type = string }
output "droplet_ip" { value = digitalocean_droplet.main.ipv4_address }
output "data_device" { value = "/dev/disk/by-id/scsi-0DO_Volume_${digitalocean_volume.data.name}" }
