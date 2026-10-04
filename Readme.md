# Autonomous Schema Drift Detection & Semantic Mapping Healer

> **AI-assisted schema drift detection, semantic understanding, mapping repair, validation, and release governance for enterprise integration systems.**

[![Release](https://img.shields.io/badge/release-v0.1.0-blue)](https://github.com/santoshbyte/schema-drift-backend/releases)
[![Status](https://img.shields.io/badge/status-Proof%20of%20Concept-orange)](https://github.com/santoshbyte/schema-drift-backend)
[![AI](https://img.shields.io/badge/AI-Google%20Gemini-purple)](https://ai.google.dev/)
[![Backend](https://img.shields.io/badge/backend-Python%20%7C%20Node.js-green)](https://github.com/santoshbyte/schema-drift-backend)
[![Frontend](https://img.shields.io/badge/frontend-React%20%2B%20Vite-61DAFB)](https://github.com/santoshbyte/schema-drift-dashboard)

---

## Table of Contents

- [Overview](#overview)
- [Problem Statement](#problem-statement)
- [Project Objective](#project-objective)
- [Core Idea](#core-idea)
- [Autonomous Pipeline](#autonomous-pipeline)
- [System Architecture](#system-architecture)
- [Repository Architecture](#repository-architecture)
- [Component Architecture](#component-architecture)
- [End-to-End Data Flow](#end-to-end-data-flow)
- [1. Detect — Schema Drift Detection](#1-detect--schema-drift-detection)
- [2. Understand — Semantic Analysis](#2-understand--semantic-analysis)
- [3. Heal — Mapping Repair](#3-heal--mapping-repair)
- [4. Validate — Repair Validation](#4-validate--repair-validation)
- [5. Decide — Confidence Gate](#5-decide--confidence-gate)
- [6. Audit — Runtime Traceability](#6-audit--runtime-traceability)
- [AI / Gemini Architecture](#ai--gemini-architecture)
- [Generic Mapping Healing](#generic-mapping-healing)
- [Multi-Field Schema Drift](#multi-field-schema-drift)
- [Test Scenarios](#test-scenarios)
- [Heavy Employee Scenario](#heavy-employee-scenario)
- [Frontend Control Plane](#frontend-control-plane)
- [API](#api)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Backend](#running-the-backend)
- [Running the Frontend](#running-the-frontend)
- [Security](#security)
- [Release Governance](#release-governance)
- [Current Capabilities](#current-capabilities)
- [Current Limitations](#current-limitations)
- [Roadmap](#roadmap)
- [Release History](#release-history)
- [Why This Architecture](#why-this-architecture)
- [SAP CPI / Integration Suite Relevance](#sap-cpi--integration-suite-relevance)
- [Future Enterprise Architecture](#future-enterprise-architecture)
- [Project Documentation](#project-documentation)
- [Contributing](#contributing)
- [License](#license)

---

# Overview

Enterprise integration systems depend on stable data contracts, schemas, APIs, and transformation mappings.

A change in an upstream system can break a downstream integration even when the business meaning of the data remains unchanged.

For example, an upstream employee system may change:

```text
empName
