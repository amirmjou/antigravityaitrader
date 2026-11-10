---
name: gcp-hardened-trader-deployer
description: Playbook for deploying 24/7 autonomous trading bots to Google Cloud Platform with zero-trust hardening. Covers e2-micro Always-Free provisioning, UFW perimeter defense, systemd sandboxing, and private repository deployment patterns.
---

# GCP Hardened Trader Deployer

Specialist in provisioning, securing, and operating 24/7 autonomous crypto trading daemons on Google Cloud Platform (GCP).

## Reference System Usage

* **For Deployment & Systemd Architecture:** Consult `references/patterns.md` for turnkey setup scripts, firewall policies, and systemd units.
* **For Private Repositories & 404 Pitfalls:** Consult `references/sharp_edges.md` for Cloud Shell authentication mechanics, raw GitHub 404 traps, and cffi sandbox issues.
* **For Security Auditing:** Consult `references/validations.md` for perimeter audit checklists and secret permission verification.
